from __future__ import annotations

import html

from aiogram.exceptions import TelegramBadRequest

from app.game.rules import build_zone_roles
from app.keyboards import host_phase_keyboard
from app.models import Game, utc_ts
from app.service import GameError
from app.zone_service import ZoneGameService


class PlaytestGameService(ZoneGameService):
    """Playtest-v2 flow tweaks layered over the Zone game service."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The group asked for 3 minutes. Older .env files may still contain 240.
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
                game.phase_deadline = utc_ts() + self.settings.discussion_seconds
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
            f"⏱ На знайомство: <b>{self.settings.discussion_seconds} сек.</b>",
        )
        try:
            await self.bot.send_message(
                game.host_user_id,
                "🧭 <b>ПДА ведучого</b>\n\n"
                "Етап: <b>🔥 Знайомство</b>\n"
                "Якщо всі вже познайомилися — завершуй етап раніше.",
                reply_markup=host_phase_keyboard(game),
            )
        except Exception:
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
