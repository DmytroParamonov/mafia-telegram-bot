from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from app.config import Settings
from app.db import init_db, make_engine, make_session_factory
from app.handlers import router
from app.playtest_service import PlaytestGameService
from app.role_cards import prepare_role_card_pack
from app.stalker_theme import StalkerBot
from app.test_mode import router as test_router
from app.zone_handlers import router as zone_router


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    settings = Settings()
    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    await init_db(engine)

    card_count = prepare_role_card_pack()
    logging.info("Ready PDA role-card pack: %s cards", card_count)

    bot = StalkerBot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    me = await bot.get_me()
    game_service = PlaytestGameService(
        bot=bot,
        session_factory=session_factory,
        bot_username=me.username or str(me.id),
        settings=settings,
    )

    await bot.set_my_commands(
        [
            BotCommand(command="stalker", description="☢️ Зібрати ходку в Зону"),
            BotCommand(command="test", description="🧪 Тестовий полігон ПДА"),
            BotCommand(command="stats", description="📟 Моя статистика"),
            BotCommand(command="check", description="🛡 Перевірити права бота"),
            BotCommand(command="help", description="🔥 Правила ходки"),
        ]
    )

    dispatcher = Dispatcher()
    # Specific commands first, generic private PDA text last. Otherwise a broad
    # private-text handler can consume slash commands before /help, /stats, etc.
    dispatcher.include_router(test_router)
    dispatcher.include_router(router)
    dispatcher.include_router(zone_router)
    scheduler_task = asyncio.create_task(game_service.phase_loop(), name="stalker-phase-scheduler")

    try:
        logging.info("Starting STALKER game bot @%s", me.username)
        await dispatcher.start_polling(bot, game_service=game_service)
    finally:
        scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler_task
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
