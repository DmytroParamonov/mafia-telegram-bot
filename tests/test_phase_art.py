from pathlib import Path

from app.game.rules import ROLE_TITLES, Role
from app.phase_art import ensure_phase_art_dir, phase_art_kind_for_text, phase_art_path
from app.phase_art_bot import kaimanovize_text
from app.private_role_art import ROLE_ART


def test_doctor_is_kaimanov_everywhere() -> None:
    assert ROLE_TITLES[Role.DOCTOR.value] == "💉 Доктор Кайманов"
    assert ROLE_ART[Role.DOCTOR.value][0].internal_name == "Доктор Кайманов"
    assert kaimanovize_text("💉 Польовий медик") == "💉 Доктор Кайманов"


def test_phase_text_routes_to_day_and_night_art() -> None:
    assert phase_art_kind_for_text("🌘 <b>Ніч у Зоні — ходка 2</b>") == "night"
    assert phase_art_kind_for_text("🌅 <b>Світанок у Зоні</b>\n\nТиха ніч") == "day"
    assert phase_art_kind_for_text("🔥 <b>Сходка біля багаття</b>") == "day"
    assert phase_art_kind_for_text("🗳 <b>Рішення табору</b>") == "day"
    assert phase_art_kind_for_text("📟 Приватний ПДА") is None


def test_phase_art_uses_local_files(tmp_path: Path) -> None:
    ensure_phase_art_dir(root=tmp_path)
    assert tmp_path.is_dir()
    assert phase_art_path("day", root=tmp_path) is None

    day = tmp_path / "day.jpg"
    night = tmp_path / "night.png"
    day.write_bytes(b"day")
    night.write_bytes(b"night")

    assert phase_art_path("day", root=tmp_path) == day
    assert phase_art_path("night", root=tmp_path) == night
