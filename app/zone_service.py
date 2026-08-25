from __future__ import annotations

import asyncio
import html
from collections import defaultdict

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from app.models import Game, GamePlayer
from app.service import GameError, GameService
from app.zone_features import READY_SECONDS, choose_zone_event


class ZoneGameService(GameService):
    """STALKER-facing additions that leave the stable Mafia engine intact."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._ready_players: defaultdict[int, set[int]] = defaultdict(set)
        self._ready_tasks: dict[int, asyncio.Task[None]] = {}

    def _ready_keyboard(self, game_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Готовий до ходки",
                        callback_data=f"r:{game_id}",
                    )
                ]
            ]
        )

    async def _ready_view(self, game_id: int) -> tuple[str, int, int | None]:
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            if game is None:
                raise GameError("Ходку не знайдено.")
            players = await self._players(session, game_id)

        ready = self._ready_players[game_id]
        lines = []
        for player in players:
            mark = "✅" if player.user_id in ready else "⏳"
            lines.append(f"{mark} {html.escape(player.display_name)}")

        text = (
            "🎒 <b>ПЕРЕВІРКА СПОРЯДЖЕННЯ</b>\n\n"
            "Перед виходом кожен сталкер має підтвердити готовність у своєму ПДА.\n\n"
            + "\n".join(lines)
            + f"\n\n⏱ На підтвердження: <b>{READY_SECONDS} сек.</b>"
        )
        return text, game.chat_id, game.lobby_message_id

    async def _refresh_ready_view(self, game_id: int) -> None:
        text, chat_id, message_id = await self._ready_view(game_id)
        if message_id is None:
            return
        try:
            await self.bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=None,
            )
        except Exception:
            # Readiness is a convenience layer; failure to refresh must not break the game.
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
            raise GameError(
                f"Потрібно щонайменше {self.settings.min_players} сталкерів. Зараз: {len(players)}."
            )

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
            except Exception:
                pass

        self._ready_tasks[game_id] = asyncio.create_task(
            self._ready_timeout(game_id),
            name=f"ready-check-{game_id}",
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
            await super().start_game(game_id, game.host_user_id)
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
            missing = [
                html.escape(player.display_name)
                for player in players
                if player.user_id not in ready
            ]
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

    async def join_game(self, game_id: int, tg_user):
        if game_id in self._ready_tasks:
            raise GameError("Група вже перевіряє спорядження. Дочекайся завершення перевірки.")
        return await super().join_game(game_id, tg_user)

    async def leave_game(self, game_id: int, user_id: int) -> None:
        if game_id in self._ready_tasks:
            raise GameError("Під час перевірки спорядження вийти з групи не можна.")
        await super().leave_game(game_id, user_id)

    async def toggle_setting(self, game_id: int, host_user_id: int, setting_name: str) -> None:
        if game_id in self._ready_tasks:
            raise GameError("Під час перевірки спорядження налаштування вже не змінюються.")
        await super().toggle_setting(game_id, host_user_id, setting_name)

    async def cancel_lobby(self, game_id: int, host_user_id: int) -> None:
        task = self._ready_tasks.pop(game_id, None)
        if task is not None:
            task.cancel()
        self._ready_players.pop(game_id, None)
        await super().cancel_lobby(game_id, host_user_id)

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
        await super()._announce_night(game_id)

    async def _resolve_night(self, game_id: int) -> None:
        await super()._resolve_night(game_id)
        # If the game survived the night and moved into discussion, sometimes add
        # a harmless daytime Zone event. Events are atmospheric and never alter rules.
        async with self.session_factory() as session:
            game = await session.get(Game, game_id)
            should_event = game is not None and game.status == "active" and game.phase == "discussion"
        if should_event:
            await self._maybe_zone_event(game_id, "day")
