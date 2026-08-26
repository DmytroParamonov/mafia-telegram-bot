from __future__ import annotations

import html

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
from app.keyboards import host_phase_keyboard
from app.models import Game, utc_ts
from app.role_cards import load_ready_role_card
from app.service import GameError
from app.zone_features import INTRO_SECONDS, callsigns_for
from app.zone_service import ZoneGameService


class PlaytestGameService(ZoneGameService):
    """Playtest-v3 flow tweaks layered over the Zone game service."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The group settled on 3 minutes for regular daytime discussion.
        self.settings.discussion_seconds = 180

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
                await session.commit()

        if lobby_message_id:
            try:
                await self.bot.edit_message_text(
                    "☢️ <b>Група зібрана. Ходка почалася!</b>\n\n"
                    "Номери, позивні та ролі вже надійшли на особисті ПДА. "
                    "Перед першою ніччю — знайомство біля багаття.",
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

            try:
                image = load_ready_role_card(role, callsign)
                await self.bot.send_photo(
                    player.user_id,
                    BufferedInputFile(
                        image,
                        filename=f"pda_{role}_{callsign}.jpg",
                    ),
                    caption=caption,
                )
            except (OSError, ValueError):
                # The ready pack is rebuilt automatically on the next request. If the
                # filesystem itself is unavailable, the complete text card still works.
                try:
                    await self.bot.send_message(player.user_id, caption)
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

    async def _begin_first_night(self, game_id: int) -> None:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None or game.status != "active" or game.phase != "intro":
                return
            game.phase = "night"
            game.phase_deadline = utc_ts() + self.settings.night_seconds
            await session.commit()
        await self._announce_night(game_id)

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

        if game.phase == "intro":
            await self._begin_first_night(game_id)
            return

        await super().advance_phase(
            game_id,
            host_user_id=host_user_id,
            expected_day=expected_day,
            expected_phase=expected_phase,
        )
