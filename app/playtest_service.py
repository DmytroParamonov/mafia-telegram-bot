from __future__ import annotations

import html
from collections import defaultdict

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile

from app.game.rules import (
    MAFIA_ROLES,
    ROLE_DESCRIPTIONS,
    ROLE_FACTIONS,
    ROLE_TITLES,
    Role,
    build_zone_roles,
)
from app.keyboards import host_phase_keyboard, role_card_help_keyboard
from app.live_zone import live_zone_effect, phase_seconds
from app.models import Game, utc_ts
from app.private_role_art import load_private_role_art, role_art_assignments
from app.role_cards import load_ready_role_card
from app.service import GameError
from app.zone_features import INTRO_SECONDS, callsigns_for
from app.zone_service import ZoneGameService


class PlaytestGameService(ZoneGameService):
    """Current STALKER MAFIA playtest flow layered over the Zone service."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The group settled on 3 minutes for regular daytime discussion.
        self.settings.discussion_seconds = 180

    async def _lobby_view(self, game_id: int) -> tuple[str, object]:
        text, markup = await super()._lobby_view(game_id)
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None:
                raise GameError("Ходку не знайдено.")

        if game.live_zone:
            mode = (
                "☢️ <b>Режим: Жива Зона</b>\n"
                "Події можуть реально змінювати час нічних дій, сходки або голосування."
            )
        else:
            mode = (
                "🎯 <b>Режим: Класична ходка</b>\n"
                "Події Зони атмосферні й не змінюють правила або таймери."
            )
        return f"{text}\n\n{mode}", markup

    async def toggle_setting(self, game_id: int, host_user_id: int, setting_name: str) -> None:
        if setting_name != "toggle_live_zone":
            await super().toggle_setting(game_id, host_user_id, setting_name)
            return
        if game_id in self._ready_tasks:
            raise GameError("Під час перевірки спорядження режим уже не змінюється.")

        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if game is None or game.status != "lobby":
                    raise GameError("Режим уже не можна змінювати.")
                if game.host_user_id != host_user_id:
                    raise GameError("Режим може змінювати лише старший групи.")
                game.live_zone = not game.live_zone
                await session.commit()
        await self.refresh_lobby(game_id)

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
                game.phase = "intro"
                game.day_number = 1
                game.vote_round = 0
                game.started_at = utc_ts()
                game.phase_deadline = utc_ts() + INTRO_SECONDS
                lobby_message_id = game.lobby_message_id
                chat_id = game.chat_id
                live_zone = game.live_zone
                await session.commit()

        if lobby_message_id:
            mode_line = (
                "\n☢️ Активовано режим <b>«Жива Зона»</b>. Події можуть впливати на хід партії."
                if live_zone
                else ""
            )
            try:
                await self.bot.edit_message_text(
                    "☢️ <b>Група зібрана. Ходка почалася!</b>\n\n"
                    "Номери, позивні та ролі вже надійшли на особисті ПДА. "
                    "Перед першою ніччю — знайомство біля багаття."
                    f"{mode_line}",
                    chat_id=chat_id,
                    message_id=lobby_message_id,
                    reply_markup=None,
                )
            except TelegramBadRequest:
                pass

        await self._send_role_cards(game_id)
        await self._announce_intro(game_id)

    async def _send_role_cards(self, game_id: int) -> None:
        async with self.session_factory() as session:
            players = await self._players(session, game_id)

        labels = self._labels(game_id, players)
        callsigns = callsigns_for(game_id, [player.user_id for player in players])
        bandits = [player for player in players if player.role in MAFIA_ROLES]

        users_by_role: dict[str, list[int]] = defaultdict(list)
        for player in players:
            users_by_role[player.role or Role.CIVILIAN.value].append(player.user_id)

        authored_art = {}
        for role, user_ids in users_by_role.items():
            try:
                authored_art.update(role_art_assignments(game_id, role, user_ids))
            except ValueError:
                # Future custom balances may contain more copies of a role than
                # the authored pack. Those players fall back to generated cards.
                pass

        for player in players:
            role = player.role or Role.CIVILIAN.value
            callsign = callsigns[player.user_id]
            caption = (
                f"📟 <b>{html.escape(labels[player.user_id])}</b>\n\n"
                f"Твоя роль: <b>{ROLE_TITLES[role]}</b>\n"
                f"Фракція: <b>{ROLE_FACTIONS[role]}</b>\n\n"
                f"{ROLE_DESCRIPTIONS[role]}"
            )
            if role in MAFIA_ROLES:
                allies = [ally for ally in bandits if ally.user_id != player.user_id]
                if allies:
                    caption += "\n\n🤝 <b>Твоя братва:</b>\n" + "\n".join(
                        f"• {html.escape(labels[ally.user_id])}" for ally in allies
                    )
                else:
                    caption += "\n\n🤝 Цієї ходки працюєш один."
            caption += "\n\n📵 Не світи ПДА іншим."
            markup = role_card_help_keyboard(game_id)

            art = authored_art.get(player.user_id)
            try:
                if art is not None:
                    image = load_private_role_art(art)
                    filename = f"pda_{role}_{art.asset_key}.jpg"
                else:
                    image = load_ready_role_card(role, callsign)
                    filename = f"pda_{role}_{callsign}.jpg"
                await self.bot.send_photo(
                    player.user_id,
                    BufferedInputFile(image, filename=filename),
                    caption=caption,
                    reply_markup=markup,
                )
            except (OSError, ValueError):
                # If authored/generated art cannot be read, the complete text
                # card still keeps the game playable.
                try:
                    await self.bot.send_message(player.user_id, caption, reply_markup=markup)
                except TelegramForbiddenError:
                    pass
            except TelegramForbiddenError:
                pass

    async def _announce_intro(self, game_id: int) -> None:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active" or game.phase != "intro":
                return
            players = await self._players(session, game_id, alive_only=True)

        all_players = await self._all_players(game_id)
        labels = self._labels(game_id, all_players)
        roster = "\n".join(
            f"• {html.escape(labels[player.user_id])}" for player in players
        )

        await self.bot.send_message(
            game.chat_id,
            "🔥 <b>ЗНАЙОМСТВО БІЛЯ БАГАТТЯ</b>\n\n"
            "Група щойно зібралася. Перед першою ніччю кожен може коротко представитися, "
            "назвати свій позивний і сказати кілька слів про себе.\n\n"
            f"{roster}\n\n"
            "На цьому етапі <b>немає голосування і нічних дій</b>. Це просто перше знайомство.\n"
            f"⏱ На знайомство: <b>{INTRO_SECONDS} сек.</b>",
        )
        try:
            await self.bot.send_message(
                game.host_user_id,
                "🧭 <b>ПДА ведучого</b>\n\n"
                "Етап: <b>🔥 Знайомство</b>\n"
                "Якщо всі вже познайомилися — завершуй етап раніше.",
                reply_markup=host_phase_keyboard(game),
            )
        except TelegramForbiddenError:
            pass

    async def _apply_live_zone_effect(self, game_id: int, phase: str) -> None:
        if phase not in {"night", "discussion", "voting"}:
            return

        async with self._locks[game_id]:
            async with self.session_factory() as session:
                game = await session.get(Game, game_id)
                if (
                    game is None
                    or game.status != "active"
                    or game.phase != phase
                    or not game.live_zone
                ):
                    return

                effect = live_zone_effect(game.id, game.day_number, phase)
                if effect is None:
                    return

                base_seconds = {
                    "night": self.settings.night_seconds,
                    "discussion": self.settings.discussion_seconds,
                    "voting": self.settings.voting_seconds,
                }[phase]
                seconds = phase_seconds(base_seconds, effect)
                game.phase_deadline = utc_ts() + seconds
                chat_id = game.chat_id
                await session.commit()

        await self.bot.send_message(
            chat_id,
            f"☢️ <b>ЖИВА ЗОНА — {effect.title}</b>\n\n"
            f"{effect.text}\n\n"
            f"⏱ Фактичний час цього етапу: <b>{seconds} сек.</b>",
        )

    async def _begin_first_night(self, game_id: int) -> None:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active" or game.phase != "intro":
                return
            game.phase = "night"
            game.phase_deadline = utc_ts() + self.settings.night_seconds
            await session.commit()
        await self._announce_night(game_id)
        await self._apply_live_zone_effect(game_id, "night")

    async def rematch(self, old_game_id: int, host_user_id: int) -> Game:
        old = await self.get_game(old_game_id)
        new_game = await super().rematch(old_game_id, host_user_id)
        if not old.live_zone:
            return new_game

        async with self.session_factory() as session:
            stored = await session.get(Game, new_game.id)
            if stored is not None:
                stored.live_zone = True
                await session.commit()
        await self.refresh_lobby(new_game.id)
        return await self.get_game(new_game.id)

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

        before_phase = game.phase
        if before_phase == "intro":
            await self._begin_first_night(game_id)
            return

        await super().advance_phase(
            game_id,
            host_user_id=host_user_id,
            expected_day=expected_day,
            expected_phase=expected_phase,
        )

        after = await self.get_game(game_id)
        if after.status == "active" and after.phase != before_phase:
            await self._apply_live_zone_effect(game_id, after.phase)
