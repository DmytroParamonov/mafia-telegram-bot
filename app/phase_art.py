from __future__ import annotations

from pathlib import Path


PHASE_ART_ROOT = Path("data/phase_art")
SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
PHASE_ART_KINDS = ("day", "night")


DAY_PREFIXES = (
    "🌅 <b>Світанок у Зоні</b>",
    "🔥 <b>Сходка біля багаття</b>",
    "🔥 <b>ЗНАЙОМСТВО БІЛЯ БАГАТТЯ</b>",
    "🗳 <b>Рішення табору</b>",
    "⚖️ <b>Нічия!</b>",
)
NIGHT_PREFIXES = (
    "🌘 <b>Ніч у Зоні",
)


def ensure_phase_art_dir(*, root: Path = PHASE_ART_ROOT) -> None:
    """Create the local folder used for day/night group artwork."""
    root.mkdir(parents=True, exist_ok=True)


def phase_art_path(kind: str, *, root: Path = PHASE_ART_ROOT) -> Path | None:
    """Return a local phase image if one exists."""
    if kind not in PHASE_ART_KINDS:
        return None
    for extension in SUPPORTED_EXTENSIONS:
        candidate = root / f"{kind}{extension}"
        if candidate.is_file():
            return candidate
    return None


def phase_art_kind_for_text(text: str) -> str | None:
    """Map major public phase announcements to the day/night artwork."""
    if text.startswith(NIGHT_PREFIXES):
        return "night"
    if text.startswith(DAY_PREFIXES):
        return "day"
    return None
