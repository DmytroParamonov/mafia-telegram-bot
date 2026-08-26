from __future__ import annotations

import asyncio
import html
import time
from collections import Counter, defaultdict

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile, ChatPermissions, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import delete, func, select

from app.game.rules import (
    HOSTILE_ROLES,
    MAFIA_ROLES,
    ROLE_DESCRIPTIONS,
    ROLE_FACTIONS,
    ROLE_TITLES,
    Role,
    build_zone_roles,
    team_for_role,
    unique_vote_winner,
    zone_role_counts,
    zone_winner_for_alive_roles,
)
from app.keyboards import host_phase_keyboard, lobby_keyboard, rematch_keyboard, target_keyboard, vote_keyboard
from app.models import DayVote, Game, GamePlayer, NightAction, User, utc_ts
from app.role_cards import build_role_card
from app.service import GameError, GameService
from app.zone_features import (
    BANDIT_CHAT_SECONDS,
    LAST_WORD_SECONDS,
    READY_SECONDS,
    ZONE_MAX_PLAYERS,
    callsigns_for,
    choose_zone_event,
    night_death_line,
    quiet_night_text,
    saved_text,
)


class ZoneGameService(GameService):
    """Full STALKER game layer used by the Telegram bot."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # Keep old .env files compatible while enforcing the new playtest rules.
        self.settings.max_players = min(self.settings.max_players, ZONE_MAX_PLAYERS)
        self.settings.min_players = max(self.settings.min_players, 5)
        self.settings.night_seconds = max(self.settings.night_seconds, 90)
        self.settings.discussion_seconds = max(self.settings.discussion_seconds, 240)
        self.settings.voting_seconds = max(self.settings.voting_seconds, 90)
        self.settings.runoff_seconds = max(self.settings.runoff_seconds, 60)

        self._ready_players: defaultdict[int, set[int]] = defaultdict(set)
        self._ready_tasks: dict[int, asyncio.Task[None]] = {}
        self._mute_warning_sent: set[int] = set()

    # ------------------------------------------------------------------
    # Player labels / lobby
    # ------------------------------------------------------------------
    def _labels(self, game_id: int, players: list[GamePlayer]) -> dict[int, str]:
        user_ids = [player.user_id for player in players]
        callsigns = callsigns_for(game_id, user_ids)
        labels: dict[int, str] = {}
        for index, player in enumerate(players, start=1):
            name = player.display_name.strip() or str(player.user_id)
            if len(name) > 28:
                name = name[:27] + "…"
            labels[player.user_id] = f"№{index} «{callsigns[player.user_id]}» — {name}"
        return labels

    async def get_open_game_for_chat(self, chat_id: int) -> Game | None:
        async with self.session_factory() as session:
            return await session.scalar(
                select(Game)
                .where(Game.chat_id == chat_id, Game.status.in_(["lobby", "active"]))
                .order_by(Game.id.desc())
            )

    async def _lobby_view(self, game_id: int) -> tuple[str, object]:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None:
                raise GameError("Ходку не знайдено.")
            host = await session.get(User, game.host_user_id)
            players = await self._players(session, game_id)

        host_name = html.escape(host.display_name if host else str(game.host_user_id))
        if players:
            player_lines = "\n".join(
                f"{index}. {html.escape(player.display_name)}"
                for index, player in enumerate(players, start=1)
            )
        else:
            player_lines = "<i>Поки нікого. Старшому групи теж треба сісти до багаття.</i>"

        balance = "Баланс буде визначено автоматично, коли збереться щонайменше 5 сталкерів."
        if 5 <= len(players) <= 10:
            counts = zone_role_counts(len(players), enable_bloodsucker=game.enable_don)
            parts = [
                f"🔪 Бандити: <b>{counts[Role.MAFIA.value]}</b>",
                f"🔎 Розвідник: <b>{counts[Role.SHERIFF.value]}</b>",
                f"💉 Медик: <b>{counts[Role.DOCTOR.value]}</b>",
            ]
            if counts[Role.BLOODSUCKER.value]:
                parts.append(f"🧛 Кровосос: <b>{counts[Role.BLOODSUCKER.value]}</b>")
            parts.append(f"☢️ Вільні сталкери: <b>{counts[Role.CIVILIAN.value]}</b>")
            balance = "\n".join(parts)

        text = (
            "☢️ <b>НОВА ХОДКА В ЗОНУ</b>\n"
            "<i>Біля багаття збирається група. Але серед своїх може ховатися хто завгодно…</i>\n\n"
            f"🧭 Старший групи: <b>{host_name}</b>\n"
            f"👥 Сталкерів: <b>{len(players)}/{self.settings.max_players}</b>\n"
            f"Мінімум для виходу: <b>{self.settings.min_players}</b>\n\n"
            f"{player_lines}\n\n"
            "⚖️ <b>Баланс на цю кількість:</b>\n"
            f"{balance}\n\n"
            "⚙️ <b>Правила ходки</b>\n"
            f"🧛 Кровосос на 9–10 гравців: {'✅' if game.enable_don else '❌'}\n"
            f"☠️ Показувати ролі вибулих: {'✅' if game.reveal_roles else '❌'}\n\n"
            "Кожен учасник має відкрити особистий чат із ботом — це його ПДА."
        )
        return text, lobby_keyboard(game, self.join_url(self.bot_username, game.id))

    async def toggle_setting(self, game_id: int, host_user_id: int, setting_name: str) -> None:
        attr_map = {
            "toggle_don": "enable_don",  # reused DB flag = Bloodsucker toggle in Zone mode
            "toggle_reveal": "reveal_roles",
        }
        attr = attr_map.get(setting_name)
        if attr is None:
            raise GameError("Цей баланс фіксований для поточного тестового режиму.")
        if game_id in self._ready_tasks:
            raise GameError("Під час перевірки спорядження налаштування вже не змінюються.")

        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "lobby":
                    raise GameError("Налаштування вже не можна змінювати.")
                if game.host_user_id != host_user_id:
                    raise GameError("Налаштування може змінювати лише старший групи.")
                setattr(game, attr, not bool(getattr(game, attr)))
                await session.commit()
        await self.refresh_lobby(game_id)

    # ------------------------------------------------------------------
    # Readiness and game start
    # ------------------------------------------------------------------
    def _ready_keyboard(self, game_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Готовий до ходки", callback_data=f"r:{game_id}")]
            ]
        )

    async def _ready_view(self, game_id: int) -> tuple[str, int, int | None]:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None:
                raise GameError("Ходку не знайдено.")
            players = await self._players(session, game_id)

        ready = self._ready_players[game_id]
        lines = [
            f"{'✅' if player.user_id in ready else '⏳'} {index}. {html.escape(player.display_name)}"
            for index, player in enumerate(players, start=1)
        ]
        text = (
            "🎒 <b>ПЕРЕВІРКА СПОРЯДЖЕННЯ</b>\n\n"
            "Перед виходом кожен має підтвердити готовність у своєму ПДА.\n\n"
            + "\n".join(lines)
            + f"\n\n⏱ На підтвердження: <b>{READY_SECONDS} сек.</b>"
        )
        return text, game.chat_id, game.lobby_message_id

    async def _refresh_ready_view(self, game_id: int) -> None:
        text, chat_id, message_id = await self._ready_view(game_id)
        if message_id is None:
            return
        try:
            await self.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=None)
        except TelegramBadRequest:
            pass

    async def start_game(self, game_id: int, host_user_id: int) -> None:
        if game_id in self._ready_tasks:
            raise GameError("Перевірка готовності вже триває.")

        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "lobby":
                raise GameError("Цю ходку вже не можна запустити.")
            if game.host_user_id != host_user_id:
                raise GameError("Вирушити може лише старший групи.")
            players = await self._players(session, game_id)

        if host_user_id not in {player.user_id for player in players}:
            raise GameError("Старшому групи теж треба приєднатися до ходки.")
        if len(players) < self.settings.min_players:
            raise GameError(f"Потрібно щонайменше {self.settings.min_players} сталкерів. Зараз: {len(players)}.")
        if len(players) > ZONE_MAX_PLAYERS:
            raise GameError("У цій версії максимум 10 сталкерів.")

        self._ready_players[game_id].clear()
        await self._refresh_ready_view(game_id)
        for player in players:
            try:
                await self.bot.send_message(
                    player.user_id,
                    "📟 <b>ПДА: перевірка готовності</b>\n\n"
                    "Група готується виходити в Зону. Перевір спорядження й підтвердь, що ти на місці.",
                    reply_markup=self._ready_keyboard(game_id),
                )
            except TelegramForbiddenError:
                pass

        self._ready_tasks[game_id] = asyncio.create_task(
            self._ready_timeout(game_id), name=f"ready-check-{game_id}"
        )

    async def mark_ready(self, game_id: int, user_id: int) -> bool:
        if game_id not in self._ready_tasks:
            raise GameError("Ця перевірка готовності вже завершена.")

        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "lobby":
                raise GameError("Ходка вже почалася або була скасована.")
            players = await self._players(session, game_id)

        ids = {player.user_id for player in players}
        if user_id not in ids:
            raise GameError("Тебе немає в цій групі.")

        self._ready_players[game_id].add(user_id)
        await self._refresh_ready_view(game_id)
        if self._ready_players[game_id] >= ids:
            task = self._ready_tasks.pop(game_id, None)
            if task is not None:
                task.cancel()
            self._ready_players.pop(game_id, None)
            await self._start_zone_game(game_id, game.host_user_id)
            return True
        return False

    async def _ready_timeout(self, game_id: int) -> None:
        try:
            await asyncio.sleep(READY_SECONDS)
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "lobby":
                    return
                players = await self._players(session, game_id)
            ready = self._ready_players.get(game_id, set())
            missing = [html.escape(player.display_name) for player in players if player.user_id not in ready]
            self._ready_tasks.pop(game_id, None)
            self._ready_players.pop(game_id, None)
            await self.refresh_lobby(game_id)
            if missing:
                await self.bot.send_message(
                    game.chat_id,
                    "⏱ <b>Група не встигла зібратися.</b>\n\n"
                    "Не підтвердили готовність: " + ", ".join(missing) + ".\n"
                    "Старший групи може натиснути «🚪 Вирушаємо» ще раз.",
                )
        except asyncio.CancelledError:
            raise

    async def _start_zone_game(self, game_id: int, host_user_id: int) -> None:
        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "lobby" or game.host_user_id != host_user_id:
                    raise GameError("Ходку вже не можна запустити.")
                players = await self._players(session, game_id)
                roles = build_zone_roles(len(players), enable_bloodsucker=game.enable_don)
                for player, role in zip(players, roles, strict=True):
                    player.role = role
                    player.alive = True

                game.status = "active"
                game.phase = "night"
                game.day_number = 1
                game.vote_round = 0
                game.started_at = utc_ts()
                game.phase_deadline = utc_ts() + self.settings.night_seconds
                lobby_message_id = game.lobby_message_id
                chat_id = game.chat_id
                await session.commit()

        if lobby_message_id:
            try:
                await self.bot.edit_message_text(
                    "☢️ <b>Група зібрана. Ходка почалася!</b>\n\n"
                    "Номери, позивні, ролі та завдання вже надійшли на особисті ПДА.",
                    chat_id=chat_id,
                    message_id=lobby_message_id,
                    reply_markup=None,
                )
            except TelegramBadRequest:
                pass
        await self._send_role_cards(game_id)
        await self._announce_night(game_id)

    async def join_game(self, game_id: int, tg_user):
        if game_id in self._ready_tasks:
            raise GameError("Група вже перевіряє спорядження. Дочекайся завершення перевірки.")
        return await super().join_game(game_id, tg_user)

    async def leave_game(self, game_id: int, user_id: int) -> None:
        if game_id in self._ready_tasks:
            raise GameError("Під час перевірки спорядження вийти з групи не можна.")
        await super().leave_game(game_id, user_id)

    async def cancel_lobby(self, game_id: int, host_user_id: int) -> None:
        task = self._ready_tasks.pop(game_id, None)
        if task is not None:
            task.cancel()
        self._ready_players.pop(game_id, None)
        await super().cancel_lobby(game_id, host_user_id)

    # ------------------------------------------------------------------
    # PDA role cards / host PDA
    # ------------------------------------------------------------------
    async def _send_role_cards(self, game_id: int) -> None:
        async with self.session_factory() as session:
            players = await self._players(session, game_id)
        labels = self._labels(game_id, players)
        mafia_players = [player for player in players if player.role in MAFIA_ROLES]

        for player in players:
            role = player.role or Role.CIVILIAN.value
            caption = (
                f"📟 <b>{html.escape(labels[player.user_id])}</b>\n\n"
                f"Твоя роль: <b>{ROLE_TITLES[role]}</b>\n"
                f"Фракція: <b>{ROLE_FACTIONS[role]}</b>\n\n"
                f"{ROLE_DESCRIPTIONS[role]}"
            )
            if role in MAFIA_ROLES:
                allies = [ally for ally in mafia_players if ally.user_id != player.user_id]
                if allies:
                    caption += "\n\n🤝 <b>Твоя братва:</b>\n" + "\n".join(
                        f"• {html.escape(labels[ally.user_id])}" for ally in allies
                    )
                else:
                    caption += "\n\n🤝 Цієї ходки працюєш один."
            caption += "\n\n📵 Не світи ПДА іншим."

            try:
                image = build_role_card(
                    role=role,
                    role_title=ROLE_TITLES[role],
                    player_label=labels[player.user_id],
                    faction=ROLE_FACTIONS[role],
                    description=ROLE_DESCRIPTIONS[role],
                )
                await self.bot.send_photo(
                    player.user_id,
                    BufferedInputFile(image, filename=f"pda_role_{role}.jpg"),
                    caption=caption,
                )
            except Exception:
                # A card must never stop the game. Text remains a complete fallback.
                try:
                    await self.bot.send_message(player.user_id, caption)
                except TelegramForbiddenError:
                    pass

    async def _send_host_controls(self, game: Game) -> None:
        phase_names = {
            "night": "🌘 Ніч",
            "discussion": "🔥 Сходка",
            "voting": "🗳 Голосування",
            "runoff": "⚖️ Переголосування",
            "last_word": "📟 Останнє слово",
        }
        try:
            await self.bot.send_message(
                game.host_user_id,
                "🧭 <b>ПДА ведучого</b>\n\n"
                f"Етап: <b>{phase_names.get(game.phase, game.phase)}</b>\n"
                f"Ходка: <b>{game.day_number}</b>\n\n"
                "Можна завершити етап раніше або додати час.",
                reply_markup=host_phase_keyboard(game),
            )
        except TelegramForbiddenError:
            pass

    async def extend_phase(
        self,
        game_id: int,
        host_user_id: int,
        expected_day: int,
        expected_phase: str,
        seconds: int = 60,
    ) -> None:
        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "active":
                    raise GameError("Ходку вже завершено.")
                if game.host_user_id != host_user_id:
                    raise GameError("Ця кнопка доступна лише старшому групи.")
                if game.day_number != expected_day or game.phase != expected_phase:
                    raise GameError("Ця кнопка належить до попереднього етапу.")
                game.phase_deadline = max(game.phase_deadline or utc_ts(), utc_ts()) + seconds
                await session.commit()

    # ------------------------------------------------------------------
    # Admin permissions / dead silence
    # ------------------------------------------------------------------
    async def permission_report(self, chat_id: int) -> str:
        member = await self.bot.get_chat_member(chat_id, self.bot.id)
        if member.status not in {"administrator", "creator"}:
            return (
                "⚠️ <b>ПДА ведучого: не вистачає прав.</b>\n\n"
                "Зроби бота адміністратором групи й дозволь <b>обмежувати учасників</b>. "
                "Це потрібно, щоб вибулі автоматично замовкали до кінця ходки."
            )
        if not bool(getattr(member, "can_restrict_members", False)):
            return (
                "⚠️ Бот уже адміністратор, але немає права <b>обмежувати учасників</b>. "
                "Увімкни це право в налаштуваннях адміністратора."
            )
        return "✅ <b>Права в нормі.</b> Бот зможе автоматично заглушати вибулих і повертати голос після ходки."

    async def _mute_player(self, game: Game, user_id: int) -> None:
        try:
            await self.bot.restrict_chat_member(
                game.chat_id,
                user_id,
                permissions=ChatPermissions(can_send_messages=False),
            )
        except (TelegramBadRequest, TelegramForbiddenError):
            if game.id not in self._mute_warning_sent:
                self._mute_warning_sent.add(game.id)
                await self.bot.send_message(
                    game.chat_id,
                    "⚠️ Не можу автоматично заглушити вибулого. Дай боту право адміністратора "
                    "«обмежувати учасників» і перевір командою /check.",
                )

    async def _unmute_players(self, game: Game, players: list[GamePlayer]) -> None:
        try:
            chat = await self.bot.get_chat(game.chat_id)
            permissions = chat.permissions or ChatPermissions(can_send_messages=True)
            for player in players:
                try:
                    await self.bot.restrict_chat_member(
                        game.chat_id,
                        player.user_id,
                        permissions=permissions,
                    )
                except (TelegramBadRequest, TelegramForbiddenError):
                    pass
        finally:
            self._mute_warning_sent.discard(game.id)

    # ------------------------------------------------------------------
    # Night and secret Bandit relay
    # ------------------------------------------------------------------
    async def _maybe_zone_event(self, game_id: int, phase: str) -> None:
        event = choose_zone_event(phase)
        if event is None:
            return
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active":
                return
            chat_id = game.chat_id
        await self.bot.send_message(chat_id, event)

    async def _announce_night(self, game_id: int) -> None:
        await self._maybe_zone_event(game_id, "night")
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active" or game.phase != "night":
                return
            players = await self._players(session, game_id, alive_only=True)
        labels = self._labels(game_id, await self._all_players(game_id))
        mafia_count = sum(1 for player in players if player.role in MAFIA_ROLES)

        extra = ""
        if mafia_count >= 2:
            extra = f"\n📻 Перші {BANDIT_CHAT_SECONDS} сек. братва може писати боту в особисті — ПДА передасть повідомлення своїм."
        await self.bot.send_message(
            game.chat_id,
            f"🌘 <b>Ніч у Зоні — ходка {game.day_number}</b>\n\n"
            "Табір стих. Нічні ролі отримали завдання на ПДА."
            f"{extra}\n⏱ На ніч: <b>{self.settings.night_seconds} сек.</b>",
        )
        await self._send_host_controls(game)

        for actor in players:
            try:
                if actor.role in MAFIA_ROLES:
                    targets = [target for target in players if target.role not in MAFIA_ROLES]
                    await self.bot.send_message(
                        actor.user_id,
                        "🔪 <b>Братва: кого прибрати?</b>\n"
                        "Усі живі бандити мають вибрати одну й ту саму ціль. Різні цілі або відсутній голос = промах.",
                        reply_markup=target_keyboard(
                            game_id=game.id,
                            day_number=game.day_number,
                            action_code="k",
                            players=targets,
                            labels=labels,
                        ),
                    )
                elif actor.role == Role.BLOODSUCKER.value:
                    targets = [target for target in players if target.user_id != actor.user_id]
                    await self.bot.send_message(
                        actor.user_id,
                        "🧛 <b>Полювання Кровососа</b>\nОбери будь-яку живу ціль. Ти граєш тільки за себе.",
                        reply_markup=target_keyboard(
                            game_id=game.id,
                            day_number=game.day_number,
                            action_code="b",
                            players=targets,
                            labels=labels,
                        ),
                    )
                elif actor.role == Role.SHERIFF.value:
                    targets = [target for target in players if target.user_id != actor.user_id]
                    await self.bot.send_message(
                        actor.user_id,
                        "🔎 <b>Розвідник: кого перевірити?</b>\nПДА покаже, чи становить ціль загрозу табору.",
                        reply_markup=target_keyboard(
                            game_id=game.id,
                            day_number=game.day_number,
                            action_code="s",
                            players=targets,
                            labels=labels,
                        ),
                    )
                elif actor.role == Role.DOCTOR.value:
                    await self.bot.send_message(
                        actor.user_id,
                        "💉 <b>Польовий медик: кого підлатати?</b>\nМожна рятувати й себе.",
                        reply_markup=target_keyboard(
                            game_id=game.id,
                            day_number=game.day_number,
                            action_code="d",
                            players=players,
                            labels=labels,
                        ),
                    )
            except TelegramForbiddenError:
                pass

    async def _all_players(self, game_id: int) -> list[GamePlayer]:
        async with self.session_factory() as session:
            return await self._players(session, game_id)

    async def submit_night_action(
        self,
        *,
        game_id: int,
        day_number: int,
        actor_user_id: int,
        action_code: str,
        target_user_id: int,
    ) -> tuple[str, bool]:
        action_map = {
            "k": "mafia_kill",
            "d": "doctor_heal",
            "s": "sheriff_check",
            "b": "bloodsucker_kill",
        }
        action_type = action_map.get(action_code)
        if action_type is None:
            raise GameError("Невідома дія.")

        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "active" or game.phase != "night" or game.day_number != day_number:
                    raise GameError("Ця нічна кнопка вже застаріла.")
                alive = await self._players(session, game_id, alive_only=True)
                all_players = await self._players(session, game_id)
                by_id = {player.user_id: player for player in alive}
                labels = self._labels(game_id, all_players)
                actor = by_id.get(actor_user_id)
                target = by_id.get(target_user_id)
                if actor is None or target is None:
                    raise GameError("Сталкер уже вибув або ціль недоступна.")

                if action_type == "mafia_kill":
                    if actor.role not in MAFIA_ROLES:
                        raise GameError("На твоєму ПДА немає такої дії.")
                    if target.role in MAFIA_ROLES:
                        raise GameError("Братва своїх не чіпає.")
                    result_text = f"🔪 Ціль братви: {html.escape(labels[target.user_id])}."
                elif action_type == "doctor_heal":
                    if actor.role != Role.DOCTOR.value:
                        raise GameError("На твоєму ПДА немає такої дії.")
                    result_text = f"💉 Допомога: {html.escape(labels[target.user_id])}."
                elif action_type == "sheriff_check":
                    if actor.role != Role.SHERIFF.value or actor.user_id == target.user_id:
                        raise GameError("Ця перевірка недоступна.")
                    hostile = target.role in HOSTILE_ROLES
                    result_text = (
                        f"🔎 Розвіддані: <b>{html.escape(labels[target.user_id])}</b> — "
                        f"{'🔴 ЗАГРОЗА' if hostile else '🟢 ЧИСТО'}."
                    )
                else:
                    if actor.role != Role.BLOODSUCKER.value or actor.user_id == target.user_id:
                        raise GameError("Ця ціль недоступна.")
                    result_text = f"🧛 Ти вистежуєш: {html.escape(labels[target.user_id])}."

                await session.execute(
                    delete(NightAction).where(
                        NightAction.game_id == game_id,
                        NightAction.day_number == day_number,
                        NightAction.actor_user_id == actor_user_id,
                        NightAction.action_type == action_type,
                    )
                )
                session.add(
                    NightAction(
                        game_id=game_id,
                        day_number=day_number,
                        actor_user_id=actor_user_id,
                        action_type=action_type,
                        target_user_id=target_user_id,
                    )
                )
                await session.commit()
                complete = await self._night_is_complete(session, game_id, day_number)
        return result_text, complete

    async def _night_is_complete(self, session, game_id: int, day_number: int) -> bool:
        players = await self._players(session, game_id, alive_only=True)
        mafia_count = sum(1 for player in players if player.role in MAFIA_ROLES)
        expected = mafia_count
        expected += sum(1 for player in players if player.role == Role.DOCTOR.value)
        expected += sum(1 for player in players if player.role == Role.SHERIFF.value)
        expected += sum(1 for player in players if player.role == Role.BLOODSUCKER.value)
        actual = await session.scalar(
            select(func.count(NightAction.id)).where(
                NightAction.game_id == game_id,
                NightAction.day_number == day_number,
            )
        )
        if expected == 0 or int(actual or 0) < expected:
            return False
        if mafia_count >= 2:
            game = await session.get(Game, game_id)
            if game and game.phase_deadline:
                phase_start = game.phase_deadline - self.settings.night_seconds
                if utc_ts() < phase_start + BANDIT_CHAT_SECONDS:
                    return False
        return True

    async def relay_bandit_message(self, user_id: int, text: str) -> bool:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(GamePlayer, Game)
                    .join(Game, Game.id == GamePlayer.game_id)
                    .where(
                        GamePlayer.user_id == user_id,
                        GamePlayer.alive.is_(True),
                        GamePlayer.role.in_(MAFIA_ROLES),
                        Game.status == "active",
                        Game.phase == "night",
                    )
                    .order_by(Game.id.desc())
                )
            ).first()
            if row is None:
                return False
            player, game = row
            players = await self._players(session, game.id, alive_only=True)

        if game.phase_deadline is None:
            return False
        phase_start = game.phase_deadline - self.settings.night_seconds
        if utc_ts() > phase_start + BANDIT_CHAT_SECONDS:
            await self.bot.send_message(user_id, "📻 Канал братви вже закрито. Обирай ціль на ПДА.")
            return True

        labels = self._labels(game.id, await self._all_players(game.id))
        allies = [ally for ally in players if ally.role in MAFIA_ROLES and ally.user_id != user_id]
        if not allies:
            return False
        relay = f"📻 <b>Братва | {html.escape(labels[player.user_id])}</b>\n{html.escape(text)}"
        for ally in allies:
            try:
                await self.bot.send_message(ally.user_id, relay)
            except TelegramForbiddenError:
                pass
        return True

    async def _resolve_night(self, game_id: int) -> None:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.phase != "night" or game.status != "active":
                return
            players = await self._players(session, game_id, alive_only=True)
            all_players = await self._players(session, game_id)
            by_id = {player.user_id: player for player in players}
            actions = list(
                (
                    await session.scalars(
                        select(NightAction).where(
                            NightAction.game_id == game_id,
                            NightAction.day_number == game.day_number,
                        )
                    )
                ).all()
            )

            mafia_count = sum(1 for player in players if player.role in MAFIA_ROLES)
            mafia_targets = [action.target_user_id for action in actions if action.action_type == "mafia_kill"]
            mafia_target_id: int | None = None
            if mafia_count and len(mafia_targets) == mafia_count and len(set(mafia_targets)) == 1:
                mafia_target_id = mafia_targets[0]

            blood_target_id = next(
                (action.target_user_id for action in actions if action.action_type == "bloodsucker_kill"),
                None,
            )
            doctor_target_id = next(
                (action.target_user_id for action in actions if action.action_type == "doctor_heal"),
                None,
            )

            attacked = {target for target in (mafia_target_id, blood_target_id) if target is not None}
            saved = doctor_target_id in attacked
            victim_ids = [target for target in attacked if target != doctor_target_id]
            victims = [by_id[target] for target in victim_ids if target in by_id]
            for victim in victims:
                victim.alive = False
            game.phase_deadline = None
            await session.commit()
            reveal_roles = game.reveal_roles

        labels = self._labels(game_id, all_players)
        if victims:
            lines = []
            for victim in victims:
                suffix = f" Роль: <b>{ROLE_TITLES[victim.role or Role.CIVILIAN.value]}</b>." if reveal_roles else ""
                lines.append(night_death_line(html.escape(labels[victim.user_id]), suffix))
                await self._mute_player(game, victim.user_id)
            morning = "🌅 <b>Світанок у Зоні</b>\n\n" + "\n\n".join(lines)
        elif saved:
            morning = saved_text()
        else:
            morning = quiet_night_text()
        await self.bot.send_message(game.chat_id, morning)

        if await self._finish_if_winner(game_id):
            return

        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active":
                return
            game.phase = "discussion"
            game.phase_deadline = utc_ts() + self.settings.discussion_seconds
            alive = await self._players(session, game_id, alive_only=True)
            await session.commit()

        all_players = await self._all_players(game_id)
        labels = self._labels(game_id, all_players)
        roster = "\n".join(f"• {html.escape(labels[player.user_id])}" for player in alive)
        await self.bot.send_message(
            game.chat_id,
            "🔥 <b>Сходка біля багаття</b>\n\n"
            f"Живі учасники:\n{roster}\n\n"
            "Обговорюйте підозри. Окремо висувати кандидата не треба: після сходки кожен живий "
            "учасник отримає на ПДА список усіх живих цілей.\n"
            f"⏱ На обговорення: <b>{self.settings.discussion_seconds} сек.</b>",
        )
        await self._send_host_controls(game)
        await self._maybe_zone_event(game_id, "day")

    # ------------------------------------------------------------------
    # Voting and last word
    # ------------------------------------------------------------------
    async def _start_voting(self, game_id: int) -> None:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active" or game.phase != "discussion":
                return
            game.phase = "voting"
            game.vote_round = 1
            game.phase_deadline = utc_ts() + self.settings.voting_seconds
            players = await self._players(session, game_id, alive_only=True)
            await session.commit()

        await self.bot.send_message(
            game.chat_id,
            "🗳 <b>Рішення табору</b>\n\n"
            "Кожен живий учасник отримав таємний вибір на ПДА. Проміжні голоси ніхто не бачить.\n"
            f"⏱ На голосування: <b>{self.settings.voting_seconds} сек.</b>",
        )
        await self._send_host_controls(game)
        await self._send_ballots(game, players, players)

    async def _send_ballots(self, game: Game, voters: list[GamePlayer], candidates: list[GamePlayer]) -> None:
        labels = self._labels(game.id, await self._all_players(game.id))
        for voter in voters:
            available = [candidate for candidate in candidates if candidate.user_id != voter.user_id]
            if not available:
                continue
            try:
                await self.bot.send_message(
                    voter.user_id,
                    "🗳 <b>Кого прогнати з табору?</b>\nТвій вибір бачить лише бот.",
                    reply_markup=vote_keyboard(
                        game_id=game.id,
                        day_number=game.day_number,
                        vote_round=game.vote_round,
                        players=available,
                        labels=labels,
                    ),
                )
            except TelegramForbiddenError:
                pass

    async def _resolve_vote(self, game_id: int) -> None:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active" or game.phase not in {"voting", "runoff"}:
                return
            round_number = game.vote_round
            players = await self._players(session, game_id, alive_only=True)
            all_players = await self._players(session, game_id)
            by_id = {player.user_id: player for player in players}
            labels = self._labels(game_id, all_players)
            target_ids = list(
                (
                    await session.scalars(
                        select(DayVote.target_user_id).where(
                            DayVote.game_id == game_id,
                            DayVote.day_number == game.day_number,
                            DayVote.vote_round == round_number,
                        )
                    )
                ).all()
            )
            winner_id, leaders = unique_vote_winner(target_ids)
            counts = Counter(target_ids)
            result_lines = sorted(
                ((count, labels[target_id]) for target_id, count in counts.items() if target_id in labels),
                key=lambda item: (-item[0], item[1]),
            )
            tally = "\n".join(f"• {html.escape(name)} — {count}" for count, name in result_lines)
            if not tally:
                tally = "• Ніхто не проголосував."

            if round_number == 1 and winner_id is None and len(leaders) >= 2:
                candidates = [by_id[user_id] for user_id in leaders if user_id in by_id]
                game.phase = "runoff"
                game.vote_round = 2
                game.phase_deadline = utc_ts() + self.settings.runoff_seconds
                await session.commit()
                names = ", ".join(html.escape(labels[player.user_id]) for player in candidates)
                await self.bot.send_message(
                    game.chat_id,
                    "⚖️ <b>Нічия!</b>\n\n"
                    f"{tally}\n\nПереголосування між: <b>{names}</b>.\n"
                    f"⏱ На переголосування: <b>{self.settings.runoff_seconds} сек.</b>",
                )
                await self._send_host_controls(game)
                await self._send_ballots(game, players, candidates)
                return

            eliminated = by_id.get(winner_id) if winner_id is not None else None
            if eliminated is not None:
                eliminated.alive = False
                game.phase = "last_word"
                game.phase_deadline = utc_ts() + LAST_WORD_SECONDS
            else:
                game.phase_deadline = None
            await session.commit()
            reveal_roles = game.reveal_roles

        if eliminated is not None:
            suffix = f"\nРоль: <b>{ROLE_TITLES[eliminated.role or Role.CIVILIAN.value]}</b>." if reveal_roles else ""
            await self.bot.send_message(
                game.chat_id,
                "🗳 <b>Рішення табору</b>\n\n"
                f"{tally}\n\n🎒 Табір проганяє <b>{html.escape(labels[eliminated.user_id])}</b>.{suffix}\n\n"
                f"📟 У нього є <b>{LAST_WORD_SECONDS} сек.</b> на останнє слово.",
            )
            await self._mute_player(game, eliminated.user_id)
            try:
                await self.bot.send_message(
                    eliminated.user_id,
                    "📟 <b>Останнє слово</b>\n\n"
                    f"У тебе {LAST_WORD_SECONDS} секунд. Напиши <b>одне текстове повідомлення</b> — "
                    "бот передасть його в табір. Штучного ліміту символів немає.",
                )
            except TelegramForbiddenError:
                pass
            await self._send_host_controls(game)
            return

        await self.bot.send_message(
            game.chat_id,
            "🗳 <b>Рішення табору</b>\n\n"
            f"{tally}\n\n🤷 Рішення немає. Сьогодні ніхто не залишає табір.",
        )
        if await self._finish_if_winner(game_id):
            return
        await self._begin_next_night(game_id)

    async def _last_word_target(self, game: Game) -> int | None:
        async with self.session_factory() as session:
            targets = list(
                (
                    await session.scalars(
                        select(DayVote.target_user_id).where(
                            DayVote.game_id == game.id,
                            DayVote.day_number == game.day_number,
                            DayVote.vote_round == game.vote_round,
                        )
                    )
                ).all()
            )
        winner, _ = unique_vote_winner(targets)
        return winner

    async def submit_last_word(self, user_id: int, text: str) -> bool:
        async with self.session_factory() as session:
            row = (
                await session.execute(
                    select(GamePlayer, Game)
                    .join(Game, Game.id == GamePlayer.game_id)
                    .where(
                        GamePlayer.user_id == user_id,
                        Game.status == "active",
                        Game.phase == "last_word",
                    )
                    .order_by(Game.id.desc())
                )
            ).first()
            if row is None:
                return False
            player, game = row
        if await self._last_word_target(game) != user_id:
            return False

        labels = self._labels(game.id, await self._all_players(game.id))
        await self.bot.send_message(
            game.chat_id,
            f"📟 <b>Останнє слово {html.escape(labels[player.user_id])}:</b>",
        )
        # Telegram itself limits one message to 4096 chars; there is no game-specific limit.
        for start in range(0, len(text), 4000):
            await self.bot.send_message(game.chat_id, text[start : start + 4000], parse_mode=None)
        await self.bot.send_message(user_id, "✅ Останнє слово передано в табір.")
        await self._complete_last_word(game.id)
        return True

    async def handle_private_text(self, user_id: int, text: str) -> bool:
        if await self.submit_last_word(user_id, text):
            return True
        return await self.relay_bandit_message(user_id, text)

    async def _complete_last_word(self, game_id: int) -> None:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active" or game.phase != "last_word":
                return
            game.phase_deadline = None
            await session.commit()
        if await self._finish_if_winner(game_id):
            return
        await self._begin_next_night(game_id)

    async def advance_phase(
        self,
        game_id: int,
        *,
        host_user_id: int | None = None,
        expected_day: int | None = None,
        expected_phase: str | None = None,
    ) -> None:
        game = await self.get_game(game_id)
        if host_user_id is not None and game.host_user_id != host_user_id:
            raise GameError("Ця кнопка доступна лише старшому групи.")
        if expected_day is not None and game.day_number != expected_day:
            raise GameError("Ця кнопка належить до попереднього етапу.")
        if expected_phase is not None and game.phase != expected_phase:
            raise GameError("Ця кнопка належить до попереднього етапу.")
        if game.phase == "last_word":
            await self._complete_last_word(game_id)
            return
        await super().advance_phase(
            game_id,
            host_user_id=host_user_id,
            expected_day=expected_day,
            expected_phase=expected_phase,
        )

    # ------------------------------------------------------------------
    # Win conditions / stats / cleanup
    # ------------------------------------------------------------------
    async def _finish_if_winner(self, game_id: int) -> bool:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active":
                return game is not None and game.status == "finished"
            alive = await self._players(session, game_id, alive_only=True)
            winner = zone_winner_for_alive_roles([player.role or Role.CIVILIAN.value for player in alive])
            if winner is None:
                return False
            all_players = await self._players(session, game_id)
            game.status = "finished"
            game.phase = "finished"
            game.phase_deadline = None
            game.winner = winner
            game.finished_at = utc_ts()
            await session.commit()

        await self._unmute_players(game, all_players)
        labels = self._labels(game_id, all_players)
        headlines = {
            "city": "☢️ <b>СТАЛКЕРИ ЗАЧИСТИЛИ ТАБІР!</b>",
            "mafia": "💀 <b>БАНДИТИ ЗАХОПИЛИ ТАБІР!</b>",
            "bloodsucker": "🧛 <b>КРОВОСОС ЗАЛИШИВСЯ ОСТАННІМ!</b>",
        }
        roster = "\n".join(
            f"• {html.escape(labels[player.user_id])} — {ROLE_TITLES.get(player.role or '', 'Невідомо')}"
            for player in all_players
        )
        await self.bot.send_message(
            game.chat_id,
            f"{headlines[winner]}\n\n📟 <b>Хто ким був у цій ходці:</b>\n{roster}",
            reply_markup=rematch_keyboard(game_id),
        )
        return True

    async def end_game(
        self,
        game_id: int,
        host_user_id: int,
        *,
        expected_day: int,
        expected_phase: str,
    ) -> None:
        await super().end_game(
            game_id,
            host_user_id,
            expected_day=expected_day,
            expected_phase=expected_phase,
        )
        game = await self.get_game(game_id)
        await self._unmute_players(game, await self._all_players(game_id))

    async def stats_text(self, user_id: int) -> str:
        async with self.session_factory() as session:
            rows = list(
                (
                    await session.execute(
                        select(GamePlayer, Game)
                        .join(Game, Game.id == GamePlayer.game_id)
                        .where(
                            GamePlayer.user_id == user_id,
                            Game.status == "finished",
                            Game.winner.in_(["city", "mafia", "bloodsucker"]),
                        )
                        .order_by(Game.id.desc())
                    )
                ).all()
            )
        total = len(rows)
        wins = sum(1 for player, game in rows if team_for_role(player.role) == game.winner)
        bandit_games = sum(1 for player, _ in rows if team_for_role(player.role) == "mafia")
        blood_games = sum(1 for player, _ in rows if team_for_role(player.role) == "bloodsucker")
        stalker_games = total - bandit_games - blood_games
        winrate = (wins / total * 100) if total else 0.0
        return (
            "📊 <b>Статистика в Зоні</b>\n\n"
            f"🎮 Ходок: <b>{total}</b>\n"
            f"🏆 Перемог: <b>{wins}</b>\n"
            f"📈 Вінрейт: <b>{winrate:.0f}%</b>\n"
            f"☢️ За сталкерів: <b>{stalker_games}</b>\n"
            f"🔪 За бандитів: <b>{bandit_games}</b>\n"
            f"🧛 За Кровососа: <b>{blood_games}</b>"
        )
