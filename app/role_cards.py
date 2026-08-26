from __future__ import annotations

from io import BytesIO
from pathlib import Path
import textwrap

from PIL import Image, ImageDraw, ImageFont

ROLE_CODES = {
    "civilian": "LONER",
    "mafia": "BANDIT",
    "don": "BOSS",
    "sheriff": "SCOUT",
    "doctor": "MEDIC",
    "bloodsucker": "BLOODSUCKER",
}

ROLE_ACCENTS = {
    "civilian": (150, 190, 105),
    "mafia": (190, 110, 90),
    "don": (195, 155, 80),
    "sheriff": (100, 170, 180),
    "doctor": (125, 185, 140),
    "bloodsucker": (160, 90, 125),
}


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_role_symbol(draw: ImageDraw.ImageDraw, role: str, x: int, y: int, accent: tuple[int, int, int]) -> None:
    # Deliberately simple vector symbols: they work identically on macOS, Linux and Docker.
    if role == "doctor":
        draw.rounded_rectangle((x + 78, y + 20, x + 122, y + 180), 8, fill=accent)
        draw.rounded_rectangle((x + 20, y + 78, x + 180, y + 122), 8, fill=accent)
    elif role == "sheriff":
        draw.ellipse((x + 20, y + 55, x + 180, y + 145), outline=accent, width=10)
        draw.ellipse((x + 82, y + 82, x + 118, y + 118), fill=accent)
    elif role == "mafia" or role == "don":
        draw.polygon([(x + 100, y + 15), (x + 175, y + 170), (x + 25, y + 170)], outline=accent)
        draw.line((x + 65, y + 105, x + 135, y + 105), fill=accent, width=12)
    elif role == "bloodsucker":
        draw.ellipse((x + 30, y + 15, x + 170, y + 155), outline=accent, width=10)
        draw.polygon([(x + 60, y + 120), (x + 85, y + 195), (x + 105, y + 125)], fill=accent)
        draw.polygon([(x + 95, y + 125), (x + 120, y + 195), (x + 140, y + 120)], fill=accent)
    else:
        # Radiation-like three-blade emblem without relying on emoji fonts.
        draw.ellipse((x + 82, y + 82, x + 118, y + 118), fill=accent)
        draw.pieslice((x + 20, y + 20, x + 180, y + 180), 210, 270, fill=accent)
        draw.pieslice((x + 20, y + 20, x + 180, y + 180), 330, 30, fill=accent)
        draw.pieslice((x + 20, y + 20, x + 180, y + 180), 90, 150, fill=accent)
        draw.ellipse((x + 58, y + 58, x + 142, y + 142), fill=(16, 22, 17))
        draw.ellipse((x + 86, y + 86, x + 114, y + 114), fill=accent)


def build_role_card(
    *,
    role: str,
    role_title: str,
    player_label: str,
    faction: str,
    description: str,
) -> bytes:
    width, height = 1200, 700
    accent = ROLE_ACCENTS.get(role, (145, 180, 110))
    image = Image.new("RGB", (width, height), (13, 18, 14))
    draw = ImageDraw.Draw(image)

    # PDA frame + CRT scan lines.
    draw.rounded_rectangle((28, 28, width - 28, height - 28), 28, outline=accent, width=5)
    draw.rounded_rectangle((48, 48, width - 48, height - 48), 22, outline=(55, 75, 57), width=2)
    for y in range(58, height - 58, 6):
        draw.line((58, y, width - 58, y), fill=(17, 25, 18), width=1)

    header_font = _font(30, bold=True)
    title_font = _font(66, bold=True)
    body_font = _font(30)
    small_font = _font(24)

    draw.text((82, 78), "PDA // ZONE NETWORK", font=header_font, fill=accent)
    draw.text((82, 128), "ROLE CARD", font=small_font, fill=(120, 140, 120))
    draw.line((82, 174, width - 82, 174), fill=(65, 88, 67), width=2)

    _draw_role_symbol(draw, role, 855, 210, accent)

    try:
        draw.text((82, 220), role_title, font=title_font, fill=(225, 235, 220))
        draw.text((82, 305), player_label, font=body_font, fill=accent)
        draw.text((82, 355), f"Фракція: {faction}", font=body_font, fill=(180, 198, 177))
        wrapped = textwrap.wrap(description, width=52)
        y = 425
        for line in wrapped[:4]:
            draw.text((82, y), line, font=body_font, fill=(185, 195, 182))
            y += 42
    except UnicodeEncodeError:
        # Very old fallback fonts may lack Cyrillic. The Telegram caption still carries
        # the full Ukrainian card, while the image remains useful and readable.
        draw.text((82, 220), ROLE_CODES.get(role, role.upper()), font=title_font, fill=(225, 235, 220))
        draw.text((82, 315), "PERSONAL PDA ACCESS", font=body_font, fill=accent)

    draw.text((82, 620), "STALKER MAFIA // KEEP THIS PDA PRIVATE", font=small_font, fill=(95, 120, 96))

    output = BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()
