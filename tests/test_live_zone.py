import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import init_db
from app.keyboards import lobby_keyboard
from app.live_zone import live_zone_effect, phase_seconds
from app.models import Game
from app.zone_features import CALLSIGNS


def test_character_roster_is_random_role_safe_pool() -> None:
    assert len(CALLSIGNS) == 20
    assert len(set(CALLSIGNS)) == 20
    assert "Саня Кабан" in CALLSIGNS
    assert "Гоша Кекс" in CALLSIGNS
    assert "Серьога Ворон" in CALLSIGNS
    assert "Льоха Кузнєц" in CALLSIGNS


def test_live_zone_effect_is_deterministic_for_same_phase() -> None:
    first = live_zone_effect(77, 3, "discussion", chance=1.0)
    second = live_zone_effect(77, 3, "discussion", chance=1.0)
    assert first == second
    assert first is not None
    assert first.phase == "discussion"


def test_live_zone_changes_phase_time_but_keeps_minimum() -> None:
    effect = live_zone_effect(12, 1, "discussion", chance=1.0)
    assert effect is not None
    assert phase_seconds(180, effect) in {120, 150}
    assert phase_seconds(30, effect) == 30


def test_lobby_has_separate_live_zone_toggle() -> None:
    game = Game(id=5, chat_id=-100, host_user_id=1, live_zone=True)
    markup = lobby_keyboard(game, "https://t.me/example")
    buttons = [button for row in markup.inline_keyboard for button in row]
    live_button = next(button for button in buttons if button.callback_data == "l:toggle_live_zone:5")
    assert "Жива Зона" in live_button.text
    assert "✅" in live_button.text


@pytest.mark.asyncio
async def test_existing_database_gets_live_zone_column() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE games (id INTEGER PRIMARY KEY)"))

    await init_db(engine)

    async with engine.begin() as conn:
        rows = await conn.execute(text("PRAGMA table_info(games)"))
        columns = {row[1] for row in rows}
    await engine.dispose()

    assert "live_zone" in columns
