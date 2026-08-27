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
from app.economy import EconomyService
from app.economy_game_service import EconomyGameService
from app.economy_handlers import router as economy_router
from app.handlers import router
from app.phase_art import ensure_phase_art_dir
from app.phase_art_bot import PhaseArtStalkerBot
from app.private_role_art import ensure_private_role_art_dirs
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
    # EconomyService imports the economy model module before create_all(), so an
    # existing SQLite database receives the new additive tables automatically.
    economy_service = EconomyService(session_factory)
    await init_db(engine)
    await economy_service.seed_catalog()

    # Authored PDA portraits and public day/night artwork live only on the bot
    # host. The repository keeps only the code and empty folder structure.
    ensure_private_role_art_dirs()
    ensure_phase_art_dir()

    bot = PhaseArtStalkerBot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    me = await bot.get_me()
    game_service = EconomyGameService(
        bot=bot,
        session_factory=session_factory,
        bot_username=me.username or str(me.id),
        settings=settings,
        economy_service=economy_service,
    )

    await bot.set_my_commands(
        [
            BotCommand(command="stalker", description="☢️ Зібрати ходку в Зону"),
            BotCommand(command="pda", description="📟 Відкрити мій ПДА"),
            BotCommand(command="shop", description="🛒 Магазин хабару"),
            BotCommand(command="test", description="🧪 Тестовий полігон ПДА"),
            BotCommand(command="stats", description="📊 Моя статистика"),
            BotCommand(command="check", description="🛡 Перевірити права бота"),
            BotCommand(command="help", description="🔥 Правила ходки"),
        ]
    )

    dispatcher = Dispatcher()
    # Economy/PDA commands are specific and must run before the broad private
    # text handler used for Bandit relay and last words.
    dispatcher.include_router(test_router)
    dispatcher.include_router(economy_router)
    dispatcher.include_router(router)
    dispatcher.include_router(zone_router)
    scheduler_task = asyncio.create_task(game_service.phase_loop(), name="stalker-phase-scheduler")

    try:
        logging.info("Starting Mafia in the Zone bot @%s", me.username)
        await dispatcher.start_polling(
            bot,
            game_service=game_service,
            economy_service=economy_service,
        )
    finally:
        scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scheduler_task
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
