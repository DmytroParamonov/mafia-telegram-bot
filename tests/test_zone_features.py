import random

from app.stalker_theme import stalkerize_button, stalkerize_text
from app.zone_features import (
    DAY_ZONE_EVENTS,
    NIGHT_ZONE_EVENTS,
    choose_zone_event,
    night_death_text,
    quiet_night_text,
    saved_text,
)


def test_zone_event_can_be_forced_for_both_phases() -> None:
    rng = random.Random(7)
    assert choose_zone_event("night", rng=rng, chance=1.0) in NIGHT_ZONE_EVENTS
    assert choose_zone_event("day", rng=rng, chance=1.0) in DAY_ZONE_EVENTS


def test_zone_event_can_be_disabled() -> None:
    assert choose_zone_event("night", rng=random.Random(1), chance=0.0) is None


def test_night_outcomes_are_ukrainian() -> None:
    rng = random.Random(42)
    death = night_death_text("Борода", "\nРоль: <b>☢️ Вільний сталкер</b>.", rng=rng)
    assert "Борода" in death
    assert "Світанок у Зоні" in death
    assert "Роль:" in death
    assert "Город" not in death

    assert "Світанок у Зоні" in saved_text(rng=random.Random(3))
    assert "Світанок у Зоні" in quiet_night_text(rng=random.Random(4))


def test_dynamic_old_engine_death_gets_rewritten() -> None:
    source = (
        "☀️ <b>Город просыпается</b>\n\n"
        "💀 Этой ночью погиб <b>Шрам</b>.\n"
        "Его роль: <b>🧑 Мирный житель</b>."
    )
    result = stalkerize_text(source)
    assert "Шрам" in result
    assert "Вільний сталкер" in result
    assert "Город" not in result
    assert "погиб" not in result


def test_main_buttons_are_ukrainian() -> None:
    assert stalkerize_button("➕ Войти в игру") == "🔥 Сісти до багаття"
    assert stalkerize_button("🚀 Игроки набраны") == "🚪 Вирушаємо"
