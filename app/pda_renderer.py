from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps

PDA_THEME_ROOT = Path("data/pda_themes")
PDA_SIZE = (1200, 760)
SUPPORTED_BACKGROUNDS = (".png", ".jpg", ".jpeg", ".webp")

THEME_SPECS: dict[str, dict[str, object]] = {
    "pda_standard": {
        "name": "📟 Стандартний ПДА",
        "title": "PDA // ZONE NET",
        "bg": (28, 32, 25),
        "panel": (16, 20, 16, 220),
        "accent": (168, 176, 74),
        "text": (235, 238, 213),
        "muted": (171, 177, 151),
    },
    "pda_military": {
        "name": "🪖 Військовий ПДА",
        "title": "MIL-PDA // FIELD TERMINAL",
        "bg": (32, 40, 30),
        "panel": (12, 20, 13, 224),
        "accent": (127, 165, 92),
        "text": (223, 234, 211),
        "muted": (148, 170, 139),
    },
    "pda_dark": {
        "name": "🌑 Темний ПДА",
        "title": "BLACK-LINK PDA",
        "bg": (16, 20, 27),
        "panel": (7, 10, 16, 226),
        "accent": (104, 160, 211),
        "text": (227, 236, 246),
        "muted": (127, 145, 166),
    },
    "pda_red": {
        "name": "🔴 Аварійний ПДА",
        "title": "EMERGENCY PDA // SIGNAL UNSTABLE",
        "bg": (40, 16, 14),
        "panel": (24, 5, 5, 226),
        "accent": (226, 74, 49),
        "text": (255, 226, 216),
        "muted": (202, 139, 126),
    },
    "pda_field": {
        "name": "☢️ Польовий ПДА",
        "title": "FIELD PDA // ZONE NET",
        "bg": (33, 28, 20),
        "panel": (18, 14, 8, 226),
        "accent": (221, 154, 61),
        "text": (244, 229, 196),
        "muted": (185, 158, 112),
    },
    "pda_black": {
        "name": "⬛ Чорний ПДА",
        "title": "BLACK PROTOCOL // SECURE",
        "bg": (8, 9, 10),
        "panel": (2, 3, 4, 232),
        "accent": (186, 164, 108),
        "text": (238, 235, 221),
        "muted": (143, 137, 119),
    },
    "pda_legend": {
        "name": "⭐ ПДА Легенди",
        "title": "LEGEND PDA // AUTHORIZED",
        "bg": (27, 20, 36),
        "panel": (15, 9, 24, 228),
        "accent": (230, 184, 82),
        "text": (249, 239, 215),
        "muted": (190, 166, 205),
    },
}


def ensure_pda_theme_dirs() -> None:
    PDA_THEME_ROOT.mkdir(parents=True, exist_ok=True)
    for key in THEME_SPECS:
        (PDA_THEME_ROOT / key).mkdir(parents=True, exist_ok=True)


def theme_key_from_label(label: str) -> str:
    for key, spec in THEME_SPECS.items():
        if label == spec["name"]:
            return key
    lowered = label.lower()
    hints = {
        "військов": "pda_military",
        "темн": "pda_dark",
        "аварійн": "pda_red",
        "польов": "pda_field",
        "чорн": "pda_black",
        "легенд": "pda_legend",
    }
    for hint, key in hints.items():
        if hint in lowered:
            return key
    return "pda_standard"


def theme_name(theme_key: str) -> str:
    return str(THEME_SPECS.get(theme_key, THEME_SPECS["pda_standard"])["name"])


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        if bold
        else [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for candidate in candidates:
        path = Path(candidate)
        if not path.is_file():
            continue
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _find_local_background(theme_key: str) -> Path | None:
    folder = PDA_THEME_ROOT / theme_key
    for suffix in SUPPORTED_BACKGROUNDS:
        candidate = folder / f"bg{suffix}"
        if candidate.is_file():
            return candidate
    return None


def _fallback_background(theme_key: str, spec: dict[str, object]) -> Image.Image:
    width, height = PDA_SIZE
    bg = tuple(spec["bg"])
    accent = tuple(spec["accent"])
    image = Image.new("RGBA", PDA_SIZE, (*bg, 255))
    draw = ImageDraw.Draw(image, "RGBA")

    # A deliberately obvious placeholder skin. Replacing data/pda_themes/<key>/bg.png
    # swaps only the artwork; the profile renderer and store logic stay unchanged.
    for y in range(0, height, 48):
        alpha = 13 if (y // 48) % 2 == 0 else 6
        draw.rectangle((0, y, width, y + 24), fill=(*accent, alpha))
    for x in range(0, width, 80):
        draw.line((x, 0, x - 220, height), fill=(*accent, 14), width=2)

    draw.rounded_rectangle((24, 24, width - 24, height - 24), radius=34, outline=(*accent, 180), width=4)
    draw.rounded_rectangle((38, 38, width - 38, height - 38), radius=28, outline=(*accent, 58), width=2)

    # Theme-specific visual motif so every placeholder already feels different.
    if theme_key == "pda_military":
        for x in range(70, width, 190):
            draw.rectangle((x, 48, x + 90, 58), fill=(*accent, 85))
    elif theme_key == "pda_red":
        for x in range(-120, width + 120, 130):
            draw.polygon([(x, height), (x + 58, height), (x + 220, height - 120), (x + 162, height - 120)], fill=(*accent, 40))
    elif theme_key == "pda_dark":
        draw.ellipse((width - 360, -160, width + 80, 280), outline=(*accent, 54), width=5)
        draw.ellipse((width - 290, -90, width + 10, 210), outline=(*accent, 36), width=2)
    elif theme_key == "pda_black":
        for i in range(5):
            draw.rectangle((width - 310 + i * 42, 58, width - 284 + i * 42, 86), fill=(*accent, 80 + i * 20))
    elif theme_key == "pda_legend":
        draw.polygon([(width - 190, 58), (width - 160, 126), (width - 86, 134), (width - 142, 182), (width - 124, 254), (width - 190, 215), (width - 256, 254), (width - 238, 182), (width - 294, 134), (width - 220, 126)], outline=(*accent, 120))
    else:
        draw.arc((width - 300, 55, width - 80, 275), start=25, end=330, fill=(*accent, 90), width=7)

    return image


def _background(theme_key: str, spec: dict[str, object]) -> Image.Image:
    custom = _find_local_background(theme_key)
    if custom is None:
        return _fallback_background(theme_key, spec)
    try:
        with Image.open(custom) as source:
            fitted = ImageOps.fit(source.convert("RGBA"), PDA_SIZE, method=Image.Resampling.LANCZOS)
            return fitted.copy()
    except (OSError, ValueError):
        return _fallback_background(theme_key, spec)


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    size = start_size
    while size > 20:
        font = _font(size, bold=bold)
        left, _, right, _ = draw.textbbox((0, 0), text, font=font)
        if right - left <= max_width:
            return font
        size -= 2
    return _font(20, bold=bold)


def _draw_progress(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, current: int, target: int, accent: tuple[int, ...]) -> None:
    ratio = 1.0 if target <= 0 else max(0.0, min(current / target, 1.0))
    draw.rounded_rectangle((x, y, x + width, y + 18), radius=9, fill=(255, 255, 255, 28))
    if ratio > 0:
        draw.rounded_rectangle((x, y, x + max(18, int(width * ratio)), y + 18), radius=9, fill=(*accent, 220))


def render_pda_card(profile: dict[str, Any], *, user_id: int, theme_key: str | None = None) -> bytes:
    ensure_pda_theme_dirs()
    active_key = theme_key or theme_key_from_label(str(profile.get("theme", "")))
    spec = THEME_SPECS.get(active_key, THEME_SPECS["pda_standard"])
    accent = tuple(spec["accent"])
    text_color = tuple(spec["text"])
    muted = tuple(spec["muted"])
    panel = tuple(spec["panel"])

    image = _background(active_key, spec)
    draw = ImageDraw.Draw(image, "RGBA")
    width, height = PDA_SIZE

    draw.rounded_rectangle((62, 94, 748, 680), radius=28, fill=panel, outline=(*accent, 110), width=2)
    draw.rounded_rectangle((780, 94, 1138, 680), radius=28, fill=panel, outline=(*accent, 110), width=2)
    draw.rectangle((62, 66, 1138, 72), fill=(*accent, 220))

    draw.text((64, 30), str(spec["title"]), font=_font(28, bold=True), fill=(*text_color, 255))
    draw.text((878, 34), f"PDA ID // {user_id:010d}", font=_font(20), fill=(*muted, 255))

    name = str(profile.get("name", user_id))
    name_font = _fit_text(draw, name, 610, 52, bold=True)
    draw.text((96, 128), name, font=name_font, fill=(*text_color, 255))

    rank = str(profile.get("rank", "Новачок"))
    title = profile.get("title")
    draw.text((98, 205), "ЗВАННЯ", font=_font(18, bold=True), fill=(*muted, 255))
    draw.text((250, 194), rank.upper(), font=_font(30, bold=True), fill=(*accent, 255))
    if title:
        draw.text((98, 242), str(title), font=_fit_text(draw, str(title), 600, 24), fill=(*text_color, 235))

    balance = int(profile.get("balance", 0))
    lifetime = int(profile.get("lifetime_earned", 0))
    trophies = int(profile.get("trophy_count", 0))

    stat_y = 304
    stats = (
        ("СХРОН", f"{balance:,}".replace(",", " "), "хабару"),
        ("ЗАРОБЛЕНО", f"{lifetime:,}".replace(",", " "), "за весь час"),
        ("КОЛЕКЦІЯ", str(trophies), "різних трофеїв"),
    )
    for label, value, suffix in stats:
        draw.text((98, stat_y), label, font=_font(18, bold=True), fill=(*muted, 255))
        draw.text((298, stat_y - 9), value, font=_font(34, bold=True), fill=(*text_color, 255))
        draw.text((490, stat_y + 4), suffix, font=_font(19), fill=(*muted, 255))
        stat_y += 72

    next_rank = profile.get("next_rank")
    draw.text((98, 548), "ПРОГРЕС", font=_font(18, bold=True), fill=(*muted, 255))
    if next_rank:
        next_name, missing = next_rank
        threshold = lifetime + int(missing)
        draw.text((98, 580), f"До «{next_name}»: {missing} хабару", font=_font(21), fill=(*text_color, 240))
        _draw_progress(draw, 98, 620, 590, lifetime, threshold, accent)
    else:
        draw.text((98, 580), "МАКСИМАЛЬНЕ ЗВАННЯ", font=_font(23, bold=True), fill=(*accent, 255))
        _draw_progress(draw, 98, 620, 590, 1, 1, accent)

    draw.text((816, 128), "ВІТРИНА ТРОФЕЇВ", font=_font(21, bold=True), fill=(*accent, 255))
    showcase = list(profile.get("showcase") or [])
    if not showcase:
        draw.text((816, 182), "Вітрина порожня", font=_font(24), fill=(*muted, 255))
        draw.text((816, 222), "Трофеї можна виставити\nчерез розділ «Колекція».", font=_font(18), fill=(*muted, 210), spacing=8)
    else:
        y = 182
        for slot, trophy_name_value in showcase[:4]:
            draw.rounded_rectangle((812, y - 8, 1104, y + 78), radius=16, fill=(255, 255, 255, 15), outline=(*accent, 46), width=1)
            draw.text((832, y + 3), f"SLOT {slot}", font=_font(15, bold=True), fill=(*muted, 255))
            trophy_name_text = str(trophy_name_value)
            draw.text((832, y + 30), trophy_name_text, font=_fit_text(draw, trophy_name_text, 250, 20, bold=True), fill=(*text_color, 255))
            y += 104

    draw.text((816, 568), "АКТИВНИЙ СКІН", font=_font(16, bold=True), fill=(*muted, 255))
    draw.text((816, 598), str(spec["name"]), font=_fit_text(draw, str(spec["name"]), 280, 22, bold=True), fill=(*text_color, 255))
    draw.text((816, 642), "ZONE NET // ONLINE", font=_font(17, bold=True), fill=(*accent, 230))

    output = BytesIO()
    image.convert("RGB").save(output, format="PNG", optimize=True)
    return output.getvalue()
