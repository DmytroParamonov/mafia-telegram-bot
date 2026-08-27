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
from app.pda_renderer import ensure_pda_theme_dirs
from app.phase_art import ensure_phase_art_dir
from app.phase_art_bot import PhaseArtStalkerBot
from app.private_role_art import ensure_private_role_art_dirs
from app.runtime_env import load_env_value
from app.test_mode import router as test_router
from app.visual_pda_handlers import router as visual_pda_router
from app.zone_handlers import router as zone_router


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    settings = Settings()
    # pydantic-settings reads .env for Settings fields, while the economy service
    # historically used os.getenv directly. Mirror ADMIN_USER_IDS into the real
    # process environment so a normal .env line works without a special launch command.
    load_env_value("ADMIN_USER_IDS")

    engine = make_engine(settings.database_url)
    session_factory = make_session_factory(engine)
    # EconomyService imports the economy model module before create_all(), so an
    # existing SQLite database receives the new additive tables automatically.
    economy_service = EconomyService(session_factory)
    await init_db(engine)
    await economy_service.seed_catalog()

    # Authored PDA portraits, public day/night artwork and optional PDA skin
    # backgrounds live only on the bot host. GitHub keeps the rendering engine.
    ensure_private_role_art_dirs()
    ensure_phase_art_dir()
    ensure_pda_theme_dirs()

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
    # Specific routers must run before the broad private text handler. Visual
    # PDA handlers also intentionally override the older text-only /start view.
    dispatcher.include_router(test_router)
    dispatcher.include_router(visual_pda_router)
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
