from __future__ import annotations

import random
import shutil
import textwrap
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.game.rules import ROLE_FACTIONS, ROLE_TITLES, Role
from app.zone_features import CALLSIGNS

CARD_ROLES = (
    Role.CIVILIAN.value,
    Role.MAFIA.value,
    Role.SHERIFF.value,
    Role.DOCTOR.value,
    Role.BLOODSUCKER.value,
)
CARD_PACK_VERSION = "v3-pda-100"
CARD_ROOT = Path("data/role_cards_v3")

ROLE_CODES = {
    Role.CIVILIAN.value: "LONER",
    Role.MAFIA.value: "BANDIT",
    Role.SHERIFF.value: "SCOUT",
    Role.DOCTOR.value: "MEDIC",
    Role.BLOODSUCKER.value: "MUTANT",
}

ROLE_ACCENTS = {
    Role.CIVILIAN.value: (202, 137, 55),
    Role.MAFIA.value: (190, 93, 55),
    Role.SHERIFF.value: (192, 145, 62),
    Role.DOCTOR.value: (190, 153, 74),
    Role.BLOODSUCKER.value: (174, 76, 62),
}


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
        if bold
        else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial Bold.ttf" if bold else "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _card_index(callsign: str) -> int:
    try:
        return CALLSIGNS.index(callsign)
    except ValueError as exc:
        raise ValueError(f"Unknown callsign: {callsign}") from exc


def ready_role_card_path(
    role: str,
    callsign: str,
    *,
    root: Path = CARD_ROOT,
) -> Path:
    if role not in CARD_ROLES:
        raise ValueError(f"Unsupported ready-card role: {role}")
    index = _card_index(callsign)
    return root / role / f"{index:02d}.jpg"


def _draw_rust_frame(
    draw: ImageDraw.ImageDraw,
    *,
    width: int,
    height: int,
    accent: tuple[int, int, int],
    rng: random.Random,
) -> None:
    draw.rectangle((12, 12, width - 12, height - 12), fill=(8, 9, 8), outline=(55, 37, 24), width=12)
    draw.rectangle((28, 28, width - 28, height - 28), outline=(111, 69, 32), width=3)
    draw.rectangle((37, 37, width - 37, height - 37), outline=(39, 34, 27), width=4)

    for _ in range(125):
        x = rng.randrange(25, width - 25)
        y = rng.randrange(25, height - 25)
        length = rng.randrange(3, 28)
        shade = rng.choice(((88, 48, 24), (120, 65, 29), (54, 42, 29)))
        draw.line((x, y, min(width - 25, x + length), y), fill=shade, width=rng.randrange(1, 3))

    for x, y in ((27, 27), (width - 27, 27), (27, height - 27), (width - 27, height - 27)):
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=(18, 17, 13), outline=accent, width=2)
        draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=(3, 3, 3))


def _draw_scanlines(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    for y in range(115, height - 190, 5):
        draw.line((55, y, width - 55, y), fill=(17, 18, 16), width=1)


def _draw_person(draw: ImageDraw.ImageDraw, role: str, accent: tuple[int, int, int]) -> None:
    # A deliberately original, simple Zone-style portrait. The finished cards are
    # pre-rendered at startup; these vector shapes are only the pack builder.
    cx = 450
    draw.polygon(
        [(235, 660), (275, 445), (352, 365), (548, 365), (625, 445), (665, 660)],
        fill=(24, 27, 25),
        outline=(63, 57, 45),
    )
    draw.polygon(
        [(318, 390), (340, 230), (393, 175), (505, 175), (560, 232), (582, 390)],
        fill=(35, 35, 30),
        outline=(80, 65, 44),
    )
    draw.ellipse((357, 220, 543, 410), fill=(76, 60, 46), outline=(92, 73, 49), width=3)
    draw.polygon(
        [(342, 309), (386, 280), (516, 280), (557, 311), (535, 400), (365, 400)],
        fill=(28, 31, 27),
        outline=(72, 70, 57),
    )
    draw.line((390, 310, 510, 310), fill=(13, 13, 12), width=12)
    draw.ellipse((397, 294, 422, 316), fill=accent)
    draw.ellipse((478, 294, 503, 316), fill=accent)

    draw.line((332, 470, 568, 470), fill=(63, 59, 49), width=5)
    draw.line((305, 515, 595, 515), fill=(43, 45, 40), width=7)
    draw.rectangle((415, 497, 485, 535), fill=(31, 32, 28), outline=(93, 73, 47), width=2)

    if role == Role.MAFIA.value:
        draw.polygon([(310, 365), (590, 365), (550, 430), (350, 430)], fill=(54, 35, 31))
        draw.line((330, 438, 570, 438), fill=accent, width=3)
    elif role == Role.SHERIFF.value:
        draw.rectangle((300, 545, 385, 596), fill=(20, 24, 22), outline=accent, width=3)
        draw.ellipse((319, 555, 365, 588), outline=accent, width=4)
        draw.ellipse((335, 566, 350, 581), fill=accent)
    elif role == Role.DOCTOR.value:
        draw.rectangle((508, 525, 590, 607), fill=(28, 34, 29), outline=(78, 75, 58), width=2)
        draw.rectangle((541, 536, 557, 596), fill=accent)
        draw.rectangle((519, 558, 579, 574), fill=accent)
    elif role == Role.BLOODSUCKER.value:
        draw.ellipse((346, 218, 554, 418), fill=(52, 38, 36), outline=(100, 45, 42), width=4)
        for offset in (-70, -35, 0, 35, 70):
            draw.arc((cx - 100 + offset, 320, cx + 15 + offset, 510), 255, 80, fill=accent, width=10)
        draw.ellipse((397, 281, 424, 310), fill=(209, 64, 46))
        draw.ellipse((477, 281, 504, 310), fill=(209, 64, 46))
    else:
        draw.polygon([(288, 430), (342, 380), (372, 450), (325, 510)], fill=(37, 42, 35))
        draw.rectangle((530, 463, 575, 602), fill=(39, 42, 36), outline=(72, 68, 49), width=2)


def build_ready_role_card(*, role: str, callsign: str) -> bytes:
    if role not in CARD_ROLES:
        raise ValueError(f"Unsupported ready-card role: {role}")
    _card_index(callsign)

    width = 900
    height = 900
    accent = ROLE_ACCENTS[role]
    rng = random.Random(f"{CARD_PACK_VERSION}:{role}:{callsign}")

    image = Image.new("RGB", (width, height), (5, 6, 5))
    draw = ImageDraw.Draw(image)
    _draw_rust_frame(draw, width=width, height=height, accent=accent, rng=rng)

    draw.rounded_rectangle((55, 52, 845, 128), 10, fill=(3, 5, 4), outline=(72, 47, 27), width=3)
    _draw_scanlines(draw, width, height)
    _draw_person(draw, role, accent)

    callsign_font = _font(55, bold=True)
    role_font = _font(32, bold=True)
    body_font = _font(25, bold=True)
    small_font = _font(20)

    bbox = draw.textbbox((0, 0), callsign, font=callsign_font)
    text_width = bbox[2] - bbox[0]
    draw.text(((width - text_width) / 2, 57), callsign, font=callsign_font, fill=(236, 132, 27))

    draw.rounded_rectangle((55, 675, 620, 838), 9, fill=(5, 7, 6), outline=(74, 55, 34), width=3)
    draw.text((78, 699), f"ПОЗИВНИЙ / {callsign}", font=body_font, fill=(210, 202, 176))
    draw.text((78, 741), f"РОЛЬ / {ROLE_TITLES[role].split(' ', 1)[-1].upper()}", font=role_font, fill=accent)
    draw.text((78, 790), f"ФРАКЦІЯ / {ROLE_FACTIONS[role].upper()}", font=small_font, fill=(184, 178, 157))

    draw.rounded_rectangle((647, 675, 845, 838), 9, fill=(7, 8, 7), outline=(66, 48, 31), width=3)
    draw.text((670, 696), "PDA //", font=small_font, fill=(128, 111, 78))
    draw.text((670, 727), ROLE_CODES[role], font=role_font, fill=accent)
    draw.line((670, 775, 818, 775), fill=(84, 60, 34), width=2)
    draw.text((670, 790), "ZONE NET", font=small_font, fill=(118, 104, 77))

    output = BytesIO()
    image.save(output, format="JPEG", quality=88, optimize=True)
    return output.getvalue()


def prepare_role_card_pack(*, root: Path = CARD_ROOT) -> int:
    manifest = root / ".version"
    if manifest.exists() and manifest.read_text(encoding="utf-8").strip() == CARD_PACK_VERSION:
        files = list(root.glob("*/*.jpg"))
        if len(files) == len(CARD_ROLES) * len(CALLSIGNS):
            return len(files)

    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)

    count = 0
    for role in CARD_ROLES:
        role_dir = root / role
        role_dir.mkdir(parents=True, exist_ok=True)
        for callsign in CALLSIGNS:
            path = ready_role_card_path(role, callsign, root=root)
            path.write_bytes(build_ready_role_card(role=role, callsign=callsign))
            count += 1

    manifest.write_text(CARD_PACK_VERSION, encoding="utf-8")
    return count


def load_ready_role_card(
    role: str,
    callsign: str,
    *,
    root: Path = CARD_ROOT,
) -> bytes:
    path = ready_role_card_path(role, callsign, root=root)
    if not path.exists():
        prepare_role_card_pack(root=root)
    return path.read_bytes()


def build_role_card(
    *,
    role: str,
    role_title: str,
    player_label: str,
    faction: str,
    description: str,
) -> bytes:
    """Legacy fallback used by older code/tests.

    Real games now load one of the 100 pre-rendered role+callsign cards. This
    fallback remains so a missing pack can never prevent a game from starting.
    """
    del role_title, faction
    callsign = next((name for name in CALLSIGNS if f"«{name}»" in player_label), CALLSIGNS[0])
    try:
        return build_ready_role_card(role=role, callsign=callsign)
    except ValueError:
        role = Role.CIVILIAN.value
        card = Image.open(BytesIO(build_ready_role_card(role=role, callsign=callsign))).convert("RGB")
        draw = ImageDraw.Draw(card)
        font = _font(22)
        for index, line in enumerate(textwrap.wrap(description, width=48)[:3]):
            draw.text((78, 620 + index * 24), line, font=font, fill=(180, 176, 157))
        output = BytesIO()
        card.save(output, format="JPEG", quality=86, optimize=True)
        return output.getvalue()
