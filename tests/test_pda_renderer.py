from __future__ import annotations

import os
from io import BytesIO

from PIL import Image

from app.pda_renderer import PDA_SIZE, render_pda_card, theme_key_from_label
from app.runtime_env import load_env_value


def _profile() -> dict[str, object]:
    return {
        "name": "John Marston",
        "balance": 4_000,
        "lifetime_earned": 5_000,
        "rank": "Досвідчений",
        "next_rank": ("Ветеран", 2_500),
        "theme": "🌑 Темний ПДА",
        "title": "«Мисливець за хабаром»",
        "trophy_count": 2,
        "showcase": [(1, "🔵 Зуб мутанта"), (2, "🟣 Чорний детектор")],
    }


def test_visual_pda_renderer_outputs_real_png() -> None:
    payload = render_pda_card(_profile(), user_id=354512868, theme_key="pda_dark")
    with Image.open(BytesIO(payload)) as image:
        assert image.format == "PNG"
        assert image.size == PDA_SIZE


def test_theme_key_is_resolved_from_saved_label() -> None:
    assert theme_key_from_label("🌑 Темний ПДА") == "pda_dark"
    assert theme_key_from_label("☢️ Польовий ПДА") == "pda_field"
    assert theme_key_from_label("unknown") == "pda_standard"


def test_admin_ids_can_be_loaded_from_dotenv(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ADMIN_USER_IDS", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("BOT_TOKEN=test\nADMIN_USER_IDS=354512868\n", encoding="utf-8")

    assert load_env_value("ADMIN_USER_IDS", env_file) == "354512868"
    assert os.environ["ADMIN_USER_IDS"] == "354512868"
