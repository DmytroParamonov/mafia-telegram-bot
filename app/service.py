from __future__ import annotations

import asyncio
import html
import logging
import time
from collections import Counter, defaultdict

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import User as TelegramUser
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import Settings
from app.game.rules import (
    MAFIA_ROLES,
    ROLE_DESCRIPTIONS,
    ROLE_TITLES,
    Role,
    RoleSetup,
    build_roles,
    team_for_role,
    unique_vote_winner,
    winner_for_alive_roles,
)
from app.keyboards import host_phase_keyboard, lobby_keyboard, rematch_keyboard, target_keyboard, vote_keyboard
from app.models import DayVote, Game, GamePlayer, NightAction, User, utc_ts

logger = logging.getLogger(__name__)


class GameError(RuntimeError):
    pass


class GameService:
    def __init__(
        self,
        bot: Bot,
        session_factory: async_sessionmaker,
        bot_username: str,
        settings: Settings,
    ) -> None:
        self.bot = bot
        self.session_factory = session_factory
        self.bot_username = bot_username
        self.settings = settings
        self._locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)

    @staticmethod
    def join_url(bot_username: str, game_id: int) -> str:
        return f"https://t.me/{bot_username}?start=join_{game_id}"

    async def ensure_user(self, tg_user: TelegramUser) -> None:
        async with self.session_factory() as session:
            await self._upsert_user(session, tg_user)
            await session.commit()

    async def _upsert_user(self, session: AsyncSession, tg_user: TelegramUser) -> User:
        user = await session.get(User, tg_user.id)
        if user is None:
            user = User(
                id=tg_user.id,
                username=tg_user.username,
                display_name=tg_user.full_name,
            )
            session.add(user)
        else:
            user.username = tg_user.username
            user.display_name = tg_user.full_name
            user.updated_at = utc_ts()
        return user

    async def create_lobby(self, chat_id: int, chat_title: str | None, host: TelegramUser) -> Game:
        async with self.session_factory() as session:
            await self._upsert_user(session, host)
            existing = await session.scalar(
                select(Game)
                .where(Game.chat_id == chat_id, Game.status.in_(["lobby", "active"]))
                .order_by(Game.id.desc())
            )
            if existing:
                raise GameError("В этом чате уже есть активная игра или лобби.")

            game = Game(chat_id=chat_id, chat_title=chat_title, host_user_id=host.id)
            session.add(game)
            await session.commit()
            await session.refresh(game)

        text, markup = await self._lobby_view(game.id)
        message = await self.bot.send_message(chat_id, text, reply_markup=markup)
        async with self.session_factory() as session:
            stored = await session.get(Game, game.id)
            if stored:
                stored.lobby_message_id = message.message_id
                await session.commit()
        return game

    async def _lobby_view(self, game_id: int) -> tuple[str, object]:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None:
                raise GameError("Игра не найдена.")
            host = await session.get(User, game.host_user_id)
            players = list(
                (
                    await session.scalars(
                        select(GamePlayer)
                        .where(GamePlayer.game_id == game_id)
                        .order_by(GamePlayer.joined_at, GamePlayer.id)
                    )
                ).all()
            )

        host_name = html.escape(host.display_name if host else str(game.host_user_id))
        if players:
            player_lines = "\n".join(
                f"{index}. {html.escape(player.display_name)}"
                for index, player in enumerate(players, start=1)
            )
        else:
            player_lines = "<i>Пока никого. Хосту тоже нужно нажать «Войти».</i>"

        text = (
            "🎭 <b>Новая игра в Мафию</b>\n\n"
            f"👑 Хост: <b>{host_name}</b>\n"
            f"👥 Игроков: <b>{len(players)}/{self.settings.max_players}</b>\n"
            f"Минимум для старта: <b>{self.settings.min_players}</b>\n\n"
            f"{player_lines}\n\n"
            "⚙️ <b>Роли и правила</b>\n"
            f"👑 Дон: {'✅' if game.enable_don else '❌'}\n"
            f"🕵️ Комиссар: {'✅' if game.enable_sheriff else '❌'}\n"
            f"🩺 Доктор: {'✅' if game.enable_doctor else '❌'}\n"
            f"🎭 Показывать роль погибшего: {'✅' if game.reveal_roles else '❌'}\n\n"
            "Чтобы получать секретную роль и кнопки действий, вход выполняется через личку бота."
        )
        markup = lobby_keyboard(game, self.join_url(self.bot_username, game.id))
        return text, markup

    async def refresh_lobby(self, game_id: int) -> None:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "lobby" or game.lobby_message_id is None:
                return
            chat_id = game.chat_id
            message_id = game.lobby_message_id

        text, markup = await self._lobby_view(game_id)
        try:
            await self.bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=markup,
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in str(exc).lower():
                logger.warning("Could not refresh lobby %s: %s", game_id, exc)

    async def join_game(self, game_id: int, tg_user: TelegramUser) -> bool:
        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "lobby":
                    raise GameError("Это лобби уже закрыто или не существует.")

                await self._upsert_user(session, tg_user)
                existing = await session.scalar(
                    select(GamePlayer).where(
                        GamePlayer.game_id == game_id,
                        GamePlayer.user_id == tg_user.id,
                    )
                )
                if existing:
                    existing.display_name = tg_user.full_name
                    await session.commit()
                    joined = False
                else:
                    count = await session.scalar(
                        select(func.count(GamePlayer.id)).where(GamePlayer.game_id == game_id)
                    )
                    if int(count or 0) >= self.settings.max_players:
                        raise GameError("Лобби уже заполнено.")
                    session.add(
                        GamePlayer(
                            game_id=game_id,
                            user_id=tg_user.id,
                            display_name=tg_user.full_name,
                        )
                    )
                    await session.commit()
                    joined = True

        await self.refresh_lobby(game_id)
        return joined

    async def leave_game(self, game_id: int, user_id: int) -> None:
        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "lobby":
                    raise GameError("Выйти можно только пока идёт набор игроков.")
                player = await session.scalar(
                    select(GamePlayer).where(
                        GamePlayer.game_id == game_id,
                        GamePlayer.user_id == user_id,
                    )
                )
                if player is None:
                    raise GameError("Ты не находишься в этом лобби.")
                await session.delete(player)
                await session.commit()
        await self.refresh_lobby(game_id)

    async def toggle_setting(self, game_id: int, host_user_id: int, setting_name: str) -> None:
        attr_map = {
            "toggle_don": "enable_don",
            "toggle_sheriff": "enable_sheriff",
            "toggle_doctor": "enable_doctor",
            "toggle_reveal": "reveal_roles",
        }
        attr = attr_map.get(setting_name)
        if attr is None:
            raise GameError("Неизвестная настройка.")

        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "lobby":
                    raise GameError("Настройки уже нельзя менять.")
                if game.host_user_id != host_user_id:
                    raise GameError("Настройки может менять только хост.")
                setattr(game, attr, not bool(getattr(game, attr)))
                await session.commit()
        await self.refresh_lobby(game_id)

    async def cancel_lobby(self, game_id: int, host_user_id: int) -> None:
        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "lobby":
                    raise GameError("Лобби уже закрыто.")
                if game.host_user_id != host_user_id:
                    raise GameError("Отменить игру может только хост.")
                game.status = "cancelled"
                game.phase = "finished"
                game.finished_at = utc_ts()
                chat_id = game.chat_id
                message_id = game.lobby_message_id
                await session.commit()

        if message_id:
            try:
                await self.bot.edit_message_text(
                    "❌ <b>Лобби отменено хостом.</b>",
                    chat_id=chat_id,
                    message_id=message_id,
                    reply_markup=None,
                )
            except TelegramBadRequest:
                pass

    async def start_game(self, game_id: int, host_user_id: int) -> None:
        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "lobby":
                    raise GameError("Эту игру уже нельзя запустить.")
                if game.host_user_id != host_user_id:
                    raise GameError("Запустить игру может только хост.")

                players = await self._players(session, game_id)
                if host_user_id not in {player.user_id for player in players}:
                    raise GameError("Хосту тоже нужно нажать «➕ Войти в игру».")
                if len(players) < self.settings.min_players:
                    raise GameError(
                        f"Нужно минимум {self.settings.min_players} игроков. Сейчас: {len(players)}."
                    )
                if len(players) > self.settings.max_players:
                    raise GameError("Слишком много игроков.")

                roles = build_roles(
                    len(players),
                    RoleSetup(
                        enable_don=game.enable_don,
                        enable_sheriff=game.enable_sheriff,
                        enable_doctor=game.enable_doctor,
                    ),
                )
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
                        "🎭 <b>Набор закрыт. Игра началась!</b>\n\nРоли отправлены игрокам в личные сообщения.",
                        chat_id=chat_id,
                        message_id=lobby_message_id,
                        reply_markup=None,
                    )
                except TelegramBadRequest:
                    pass

            await self._send_role_cards(game_id)
            await self._announce_night(game_id)

    async def _players(
        self,
        session: AsyncSession,
        game_id: int,
        *,
        alive_only: bool = False,
    ) -> list[GamePlayer]:
        query = select(GamePlayer).where(GamePlayer.game_id == game_id)
        if alive_only:
            query = query.where(GamePlayer.alive.is_(True))
        query = query.order_by(GamePlayer.joined_at, GamePlayer.id)
        return list((await session.scalars(query)).all())

    async def _send_role_cards(self, game_id: int) -> None:
        async with self.session_factory() as session:
            players = await self._players(session, game_id)

        mafia_players = [player for player in players if player.role in MAFIA_ROLES]
        for player in players:
            role = player.role or Role.CIVILIAN.value
            text = (
                f"🎭 <b>Твоя роль: {ROLE_TITLES[role]}</b>\n\n"
                f"{ROLE_DESCRIPTIONS[role]}"
            )
            if role in MAFIA_ROLES:
                allies = [ally for ally in mafia_players if ally.user_id != player.user_id]
                if allies:
                    text += "\n\n🤝 <b>Твои союзники:</b>\n" + "\n".join(
                        f"• {html.escape(ally.display_name)} — {ROLE_TITLES[ally.role or Role.MAFIA.value]}"
                        for ally in allies
                    )
                else:
                    text += "\n\n🤝 В этой партии ты работаешь один."
            text += "\n\n🤫 Не показывай это сообщение другим игрокам."
            try:
                await self.bot.send_message(player.user_id, text)
            except TelegramForbiddenError as exc:
                logger.warning("Player %s blocked private messages: %s", player.user_id, exc)

    async def _announce_night(self, game_id: int) -> None:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active" or game.phase != "night":
                return
            players = await self._players(session, game_id, alive_only=True)

        await self.bot.send_message(
            game.chat_id,
            f"🌙 <b>Ночь {game.day_number}</b>\n\n"
            "Город засыпает. Игроки с ночными ролями получили действия в личке.\n"
            f"⏱ На ночь: {self.settings.night_seconds} сек.",
            reply_markup=host_phase_keyboard(game),
        )

        for actor in players:
            if actor.role in MAFIA_ROLES:
                targets = [target for target in players if target.role not in MAFIA_ROLES]
                await self.bot.send_message(
                    actor.user_id,
                    "🔫 <b>Мафия: кого убрать этой ночью?</b>\n"
                    "Каждый живой мафиози голосует. При ничьей выстрел сорвётся.",
                    reply_markup=target_keyboard(
                        game_id=game.id,
                        day_number=game.day_number,
                        action_code="k",
                        players=targets,
                    ),
                )

            if actor.role == Role.DON.value:
                targets = [target for target in players if target.user_id != actor.user_id]
                await self.bot.send_message(
                    actor.user_id,
                    "👑 <b>Дон: кого проверить на Комиссара?</b>",
                    reply_markup=target_keyboard(
                        game_id=game.id,
                        day_number=game.day_number,
                        action_code="o",
                        players=targets,
                    ),
                )

            if actor.role == Role.SHERIFF.value:
                targets = [target for target in players if target.user_id != actor.user_id]
                await self.bot.send_message(
                    actor.user_id,
                    "🕵️ <b>Комиссар: кого проверить?</b>",
                    reply_markup=target_keyboard(
                        game_id=game.id,
                        day_number=game.day_number,
                        action_code="s",
                        players=targets,
                    ),
                )

            if actor.role == Role.DOCTOR.value:
                await self.bot.send_message(
                    actor.user_id,
                    "🩺 <b>Доктор: кого лечить?</b>\nМожно лечить и себя.",
                    reply_markup=target_keyboard(
                        game_id=game.id,
                        day_number=game.day_number,
                        action_code="d",
                        players=players,
                    ),
                )

    async def submit_night_action(
        self,
        *,
        game_id: int,
        day_number: int,
        actor_user_id: int,
        action_code: str,
        target_user_id: int,
    ) -> tuple[str, bool]:
        action_map = {"k": "mafia_kill", "d": "doctor_heal", "s": "sheriff_check", "o": "don_check"}
        action_type = action_map.get(action_code)
        if action_type is None:
            raise GameError("Неизвестное действие.")

        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if (
                    game is None
                    or game.status != "active"
                    or game.phase != "night"
                    or game.day_number != day_number
                ):
                    raise GameError("Эта ночная кнопка уже устарела.")

                actor = await session.scalar(
                    select(GamePlayer).where(
                        GamePlayer.game_id == game_id,
                        GamePlayer.user_id == actor_user_id,
                        GamePlayer.alive.is_(True),
                    )
                )
                target = await session.scalar(
                    select(GamePlayer).where(
                        GamePlayer.game_id == game_id,
                        GamePlayer.user_id == target_user_id,
                        GamePlayer.alive.is_(True),
                    )
                )
                if actor is None or target is None:
                    raise GameError("Игрок уже выбыл или цель недоступна.")

                if action_type == "mafia_kill":
                    if actor.role not in MAFIA_ROLES:
                        raise GameError("У тебя нет такого действия.")
                    if target.role in MAFIA_ROLES:
                        raise GameError("Мафия не может стрелять в своего.")
                    result_text = f"🔫 Выбор принят: {html.escape(target.display_name)}."
                elif action_type == "doctor_heal":
                    if actor.role != Role.DOCTOR.value:
                        raise GameError("У тебя нет такого действия.")
                    result_text = f"🩺 Ты лечишь: {html.escape(target.display_name)}."
                elif action_type == "sheriff_check":
                    if actor.role != Role.SHERIFF.value or actor.user_id == target.user_id:
                        raise GameError("Недоступная проверка.")
                    is_mafia = target.role in MAFIA_ROLES
                    result_text = (
                        f"🕵️ Проверка: <b>{html.escape(target.display_name)}</b> — "
                        f"{'🔴 МАФИЯ' if is_mafia else '🟢 НЕ МАФИЯ'}."
                    )
                else:
                    if actor.role != Role.DON.value or actor.user_id == target.user_id:
                        raise GameError("Недоступная проверка.")
                    is_sheriff = target.role == Role.SHERIFF.value
                    result_text = (
                        f"👑 Проверка: <b>{html.escape(target.display_name)}</b> — "
                        f"{'🕵️ КОМИССАР' if is_sheriff else '❌ не Комиссар'}."
                    )

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

    async def _night_is_complete(self, session: AsyncSession, game_id: int, day_number: int) -> bool:
        players = await self._players(session, game_id, alive_only=True)
        expected = sum(1 for player in players if player.role in MAFIA_ROLES)
        expected += sum(1 for player in players if player.role == Role.DOCTOR.value)
        expected += sum(1 for player in players if player.role == Role.SHERIFF.value)
        expected += sum(1 for player in players if player.role == Role.DON.value)
        actual = await session.scalar(
            select(func.count(NightAction.id)).where(
                NightAction.game_id == game_id,
                NightAction.day_number == day_number,
            )
        )
        return expected > 0 and int(actual or 0) >= expected

    async def submit_vote(
        self,
        *,
        game_id: int,
        day_number: int,
        vote_round: int,
        voter_user_id: int,
        target_user_id: int,
    ) -> tuple[str, bool]:
        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                valid_phase = "voting" if vote_round == 1 else "runoff"
                if (
                    game is None
                    or game.status != "active"
                    or game.phase != valid_phase
                    or game.day_number != day_number
                    or game.vote_round != vote_round
                ):
                    raise GameError("Эта кнопка голосования уже устарела.")

                alive = await self._players(session, game_id, alive_only=True)
                by_id = {player.user_id: player for player in alive}
                voter = by_id.get(voter_user_id)
                target = by_id.get(target_user_id)
                if voter is None or target is None:
                    raise GameError("Голосовать могут только живые игроки за живых игроков.")
                if voter_user_id == target_user_id:
                    raise GameError("За себя голосовать нельзя.")

                if vote_round == 2:
                    first_round_targets = list(
                        (
                            await session.scalars(
                                select(DayVote.target_user_id).where(
                                    DayVote.game_id == game_id,
                                    DayVote.day_number == day_number,
                                    DayVote.vote_round == 1,
                                )
                            )
                        ).all()
                    )
                    _, leaders = unique_vote_winner(first_round_targets)
                    if target_user_id not in leaders:
                        raise GameError("В переголосовании можно выбирать только лидеров первого тура.")

                await session.execute(
                    delete(DayVote).where(
                        DayVote.game_id == game_id,
                        DayVote.day_number == day_number,
                        DayVote.vote_round == vote_round,
                        DayVote.voter_user_id == voter_user_id,
                    )
                )
                session.add(
                    DayVote(
                        game_id=game_id,
                        day_number=day_number,
                        vote_round=vote_round,
                        voter_user_id=voter_user_id,
                        target_user_id=target_user_id,
                    )
                )
                await session.commit()

                vote_count = await session.scalar(
                    select(func.count(DayVote.id)).where(
                        DayVote.game_id == game_id,
                        DayVote.day_number == day_number,
                        DayVote.vote_round == vote_round,
                    )
                )
                complete = int(vote_count or 0) >= len(alive)

        return f"🗳 Голос принят: {html.escape(target.display_name)}.", complete

    async def advance_phase(
        self,
        game_id: int,
        *,
        host_user_id: int | None = None,
        expected_day: int | None = None,
        expected_phase: str | None = None,
    ) -> None:
        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "active":
                    raise GameError("Игра уже завершена.")
                if host_user_id is not None and game.host_user_id != host_user_id:
                    raise GameError("Эта кнопка доступна только хосту.")
                if expected_day is not None and game.day_number != expected_day:
                    raise GameError("Эта кнопка относится к старой фазе.")
                if expected_phase is not None and game.phase != expected_phase:
                    raise GameError("Эта кнопка относится к старой фазе.")
                phase = game.phase

            if phase == "night":
                await self._resolve_night(game_id)
            elif phase == "discussion":
                await self._start_voting(game_id)
            elif phase in {"voting", "runoff"}:
                await self._resolve_vote(game_id)
            else:
                raise GameError("Эту фазу нельзя завершить вручную.")

    async def _resolve_night(self, game_id: int) -> None:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.phase != "night" or game.status != "active":
                return
            players = await self._players(session, game_id, alive_only=True)
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

            kill_targets = [
                action.target_user_id for action in actions if action.action_type == "mafia_kill"
            ]
            kill_target_id, _ = unique_vote_winner(kill_targets)
            doctor_target_id = next(
                (
                    action.target_user_id
                    for action in actions
                    if action.action_type == "doctor_heal"
                ),
                None,
            )

            victim: GamePlayer | None = None
            if kill_target_id is not None and kill_target_id != doctor_target_id:
                victim = by_id.get(kill_target_id)
                if victim:
                    victim.alive = False

            game.phase_deadline = None
            await session.commit()

            reveal_roles = game.reveal_roles
            chat_id = game.chat_id

        if victim:
            role_suffix = (
                f"\nЕго роль: <b>{ROLE_TITLES.get(victim.role or '', 'Неизвестно')}</b>."
                if reveal_roles
                else ""
            )
            morning = (
                "☀️ <b>Город просыпается</b>\n\n"
                f"💀 Этой ночью погиб <b>{html.escape(victim.display_name)}</b>."
                f"{role_suffix}"
            )
        elif kill_target_id is not None and kill_target_id == doctor_target_id:
            morning = (
                "☀️ <b>Город просыпается</b>\n\n"
                "🩺 Этой ночью было покушение, но жертва выжила. Доктор попал точно в цель."
            )
        else:
            morning = "☀️ <b>Город просыпается</b>\n\nЭтой ночью никто не погиб."

        await self.bot.send_message(chat_id, morning)
        if await self._finish_if_winner(game_id):
            return

        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active":
                return
            game.phase = "discussion"
            game.phase_deadline = utc_ts() + self.settings.discussion_seconds
            await session.commit()

        await self.bot.send_message(
            chat_id,
            "🗣 <b>Обсуждение</b>\n\n"
            f"У города есть {self.settings.discussion_seconds} сек., чтобы решить, кто подозрителен.",
            reply_markup=host_phase_keyboard(game),
        )

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
            "🗳 <b>Городское голосование</b>\n\n"
            "Каждый живой игрок получил тайный бюллетень в личке.\n"
            f"⏱ На голосование: {self.settings.voting_seconds} сек.",
            reply_markup=host_phase_keyboard(game),
        )
        await self._send_ballots(game, players, players)

    async def _send_ballots(
        self,
        game: Game,
        voters: list[GamePlayer],
        candidates: list[GamePlayer],
    ) -> None:
        for voter in voters:
            available = [candidate for candidate in candidates if candidate.user_id != voter.user_id]
            if not available:
                continue
            try:
                await self.bot.send_message(
                    voter.user_id,
                    "🗳 <b>Кого изгнать из города?</b>\nТвой голос видит только бот.",
                    reply_markup=vote_keyboard(
                        game_id=game.id,
                        day_number=game.day_number,
                        vote_round=game.vote_round,
                        players=available,
                    ),
                )
            except TelegramForbiddenError:
                logger.warning("Could not send ballot to user %s", voter.user_id)

    async def _resolve_vote(self, game_id: int) -> None:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active" or game.phase not in {"voting", "runoff"}:
                return
            round_number = game.vote_round
            players = await self._players(session, game_id, alive_only=True)
            by_id = {player.user_id: player for player in players}
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
                (
                    (count, html.escape(by_id[target_id].display_name))
                    for target_id, count in counts.items()
                    if target_id in by_id
                ),
                key=lambda item: (-item[0], item[1]),
            )
            tally = "\n".join(f"• {name} — {count}" for count, name in result_lines)
            if not tally:
                tally = "• Никто не проголосовал."

            if round_number == 1 and winner_id is None and len(leaders) >= 2:
                candidates = [by_id[user_id] for user_id in leaders if user_id in by_id]
                game.phase = "runoff"
                game.vote_round = 2
                game.phase_deadline = utc_ts() + self.settings.runoff_seconds
                await session.commit()

                names = ", ".join(html.escape(player.display_name) for player in candidates)
                await self.bot.send_message(
                    game.chat_id,
                    "⚖️ <b>Ничья!</b>\n\n"
                    f"{tally}\n\n"
                    f"Переголосование между: <b>{names}</b>.\n"
                    f"⏱ {self.settings.runoff_seconds} сек.",
                    reply_markup=host_phase_keyboard(game),
                )
                await self._send_ballots(game, players, candidates)
                return

            eliminated: GamePlayer | None = None
            if winner_id is not None:
                eliminated = by_id.get(winner_id)
                if eliminated:
                    eliminated.alive = False

            game.phase_deadline = None
            await session.commit()
            reveal_roles = game.reveal_roles
            chat_id = game.chat_id

        if eliminated:
            role_suffix = (
                f"\nРоль: <b>{ROLE_TITLES.get(eliminated.role or '', 'Неизвестно')}</b>."
                if reveal_roles
                else ""
            )
            text = (
                "🗳 <b>Результаты голосования</b>\n\n"
                f"{tally}\n\n"
                f"🚪 Город изгоняет <b>{html.escape(eliminated.display_name)}</b>."
                f"{role_suffix}"
            )
        else:
            text = (
                "🗳 <b>Результаты голосования</b>\n\n"
                f"{tally}\n\n"
                "🤷 Решения нет. Сегодня никто не покидает город."
            )
        await self.bot.send_message(chat_id, text)

        if await self._finish_if_winner(game_id):
            return
        await self._begin_next_night(game_id)

    async def _begin_next_night(self, game_id: int) -> None:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active":
                return
            game.day_number += 1
            game.vote_round = 0
            game.phase = "night"
            game.phase_deadline = utc_ts() + self.settings.night_seconds
            await session.commit()
        await self._announce_night(game_id)

    async def _finish_if_winner(self, game_id: int) -> bool:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active":
                return game is not None and game.status == "finished"
            alive = await self._players(session, game_id, alive_only=True)
            winner = winner_for_alive_roles([player.role or Role.CIVILIAN.value for player in alive])
            if winner is None:
                return False

            all_players = await self._players(session, game_id)
            game.status = "finished"
            game.phase = "finished"
            game.phase_deadline = None
            game.winner = winner
            game.finished_at = utc_ts()
            chat_id = game.chat_id
            await session.commit()

        headline = "🏙 <b>ГОРОД ПОБЕДИЛ!</b>" if winner == "city" else "🔴 <b>МАФИЯ ЗАХВАТИЛА ГОРОД!</b>"
        roster = "\n".join(
            f"• {html.escape(player.display_name)} — {ROLE_TITLES.get(player.role or '', 'Неизвестно')}"
            for player in all_players
        )
        await self.bot.send_message(
            chat_id,
            f"{headline}\n\n🎭 <b>Все роли:</b>\n{roster}",
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
        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "active":
                    raise GameError("Игра уже завершена.")
                if game.host_user_id != host_user_id:
                    raise GameError("Завершить игру может только хост.")
                if game.day_number != expected_day or game.phase != expected_phase:
                    raise GameError("Эта кнопка относится к старой фазе.")
                game.status = "cancelled"
                game.phase = "finished"
                game.phase_deadline = None
                game.finished_at = utc_ts()
                chat_id = game.chat_id
                await session.commit()
        await self.bot.send_message(chat_id, "🛑 <b>Игра завершена хостом.</b>")

    async def get_game(self, game_id: int) -> Game:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None:
                raise GameError("Игра не найдена.")
            return game

    async def validate_host_phase(
        self,
        game_id: int,
        user_id: int,
        day_number: int,
        phase: str,
    ) -> Game:
        game = await self.get_game(game_id)
        if game.status != "active" or game.host_user_id != user_id:
            raise GameError("Эта кнопка доступна только хосту активной игры.")
        if game.day_number != day_number or game.phase != phase:
            raise GameError("Эта кнопка относится к старой фазе.")
        return game

    async def rematch(self, old_game_id: int, host_user_id: int) -> Game:
        async with self._locks[old_game_id]:
            async with self.session_factory() as session:
                old = await session.get(Game, old_game_id)
                if old is None or old.status != "finished":
                    raise GameError("Реванш доступен только после завершённой игры.")
                if old.host_user_id != host_user_id:
                    raise GameError("Реванш может запустить только хост.")
                existing = await session.scalar(
                    select(Game).where(
                        Game.chat_id == old.chat_id,
                        Game.status.in_(["lobby", "active"]),
                    )
                )
                if existing:
                    raise GameError("В чате уже создана новая игра.")

                old_players = await self._players(session, old_game_id)
                new_game = Game(
                    chat_id=old.chat_id,
                    chat_title=old.chat_title,
                    host_user_id=old.host_user_id,
                    enable_don=old.enable_don,
                    enable_sheriff=old.enable_sheriff,
                    enable_doctor=old.enable_doctor,
                    reveal_roles=old.reveal_roles,
                )
                session.add(new_game)
                await session.flush()
                for player in old_players:
                    session.add(
                        GamePlayer(
                            game_id=new_game.id,
                            user_id=player.user_id,
                            display_name=player.display_name,
                        )
                    )
                await session.commit()
                await session.refresh(new_game)

        text, markup = await self._lobby_view(new_game.id)
        message = await self.bot.send_message(new_game.chat_id, text, reply_markup=markup)
        async with self.session_factory() as session:
            stored = await session.get(Game, new_game.id)
            if stored:
                stored.lobby_message_id = message.message_id
                await session.commit()
        return new_game

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
                            Game.winner.in_(["city", "mafia"]),
                        )
                        .order_by(Game.id.desc())
                    )
                ).all()
            )

        total = len(rows)
        wins = sum(1 for player, game in rows if team_for_role(player.role) == game.winner)
        mafia_games = sum(1 for player, _ in rows if team_for_role(player.role) == "mafia")
        city_games = total - mafia_games
        winrate = (wins / total * 100) if total else 0.0
        return (
            "📊 <b>Твоя статистика</b>\n\n"
            f"🎮 Игр: <b>{total}</b>\n"
            f"🏆 Побед: <b>{wins}</b>\n"
            f"📈 Винрейт: <b>{winrate:.0f}%</b>\n"
            f"🔴 За мафию: <b>{mafia_games}</b>\n"
            f"🏙 За город: <b>{city_games}</b>"
        )

    async def phase_loop(self) -> None:
        """Persistent scheduler: deadlines are stored in SQLite and survive restarts."""
        while True:
            try:
                now = int(time.time())
                async with self.session_factory() as session:
                    ids = list(
                        (
                            await session.scalars(
                                select(Game.id).where(
                                    Game.status == "active",
                                    Game.phase_deadline.is_not(None),
                                    Game.phase_deadline <= now,
                                )
                            )
                        ).all()
                    )
                for game_id in ids:
                    try:
                        await self.advance_phase(game_id)
                    except GameError:
                        pass
                    except Exception:
                        logger.exception("Failed to advance game %s", game_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Phase scheduler iteration failed")
            await asyncio.sleep(self.settings.phase_poll_seconds)
