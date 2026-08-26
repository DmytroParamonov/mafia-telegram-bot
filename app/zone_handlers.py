from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from app.service import GameError
from app.zone_service import ZoneGameService

router = Router()


@router.callback_query(F.data.startswith("r:"))
async def ready_callback(query: CallbackQuery, game_service: ZoneGameService) -> None:
    if query.from_user is None or not query.data:
        return
    parts = query.data.split(":")
    if len(parts) != 2:
        await query.answer("Некоректна кнопка.", show_alert=True)
        return

    try:
        game_id = int(parts[1])
        started = await game_service.mark_ready(game_id, query.from_user.id)
    except (ValueError, GameError) as exc:
        await query.answer(str(exc), show_alert=True)
        return

    await query.answer("✅ Готовність підтверджено.")
    if query.message:
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        if started:
            await query.message.answer("☢️ Усі готові. Група вирушила в Зону.")
        else:
            await query.message.answer("📟 ПДА: статус «готовий» передано старшому групи.")


@router.message(F.chat.type == ChatType.PRIVATE, F.text, ~F.text.startswith("/"))
async def private_pda_text(message: Message, game_service: ZoneGameService) -> None:
    """Relay ordinary PDA text without swallowing slash commands.

    Command messages must continue to the main handlers router (/help, /stats,
    /check, /stalker, /start, etc.). Previously this handler matched every text
    message first and returned for commands, which made aiogram consider the
    update handled before command handlers could see it.
    """
    if message.from_user is None or not message.text:
        return
    await game_service.handle_private_text(message.from_user.id, message.text)
