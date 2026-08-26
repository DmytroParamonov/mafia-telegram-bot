from __future__ import annotations

import base64
import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


PRIVATE_ART_ROOT = Path("assets/private_role_art_v2")


@dataclass(frozen=True, slots=True)
class PrivateRoleArt:
    internal_name: str
    role: str
    asset_key: str


# These character names are internal art labels only. They are never published
# to the group and never replace the public callsign, so the picture cannot leak
# a secret role to other players.
BANDIT_ART: tuple[PrivateRoleArt, ...] = (
    PrivateRoleArt("Саня Кабан", "mafia", "sanya_kaban"),
    PrivateRoleArt("Гоша Кекс", "mafia", "gosha_keks"),
    PrivateRoleArt("Гриша Музарука", "mafia", "grisha_muzaruka"),
    PrivateRoleArt("Жека Гнилий", "mafia", "zheka_gniliy"),
    PrivateRoleArt("Толік Барсук", "mafia", "tolik_barsuk"),
)

CIVILIAN_ART: tuple[PrivateRoleArt, ...] = (
    PrivateRoleArt("Серьога Ворон", "civilian", "seryoha_voron"),
    PrivateRoleArt("Коля Тихий", "civilian", "kolya_tikhiy"),
    PrivateRoleArt("Вадік Рижий", "civilian", "vadik_ryzhiy"),
    PrivateRoleArt("Паша Борода", "civilian", "pasha_boroda"),
    PrivateRoleArt("Діма Філін", "civilian", "dima_filin"),
    PrivateRoleArt("Ігор Крот", "civilian", "igor_krot"),
    PrivateRoleArt("Вова Сєдой", "civilian", "vova_sedoy"),
    PrivateRoleArt("Рома Яструб", "civilian", "roma_yastrub"),
    PrivateRoleArt("Макс Монах", "civilian", "maks_monakh"),
    PrivateRoleArt("Льоха Кузнєц", "civilian", "lyokha_kuznets"),
)

DOCTOR_ART: tuple[PrivateRoleArt, ...] = (
    PrivateRoleArt("Польовий медик", "doctor", "doctor"),
)

SCOUT_ART: tuple[PrivateRoleArt, ...] = (
    PrivateRoleArt("Розвідник", "sheriff", "scout"),
)

BLOODSUCKER_ART: tuple[PrivateRoleArt, ...] = (
    PrivateRoleArt("Кровосос", "bloodsucker", "bloodsucker"),
)

ROLE_ART: dict[str, tuple[PrivateRoleArt, ...]] = {
    "mafia": BANDIT_ART,
    "civilian": CIVILIAN_ART,
    "doctor": DOCTOR_ART,
    "sheriff": SCOUT_ART,
    "bloodsucker": BLOODSUCKER_ART,
}


def role_art_assignments(
    game_id: int,
    role: str,
    user_ids: Sequence[int],
) -> dict[int, PrivateRoleArt]:
    """Assign authored portraits deterministically and without duplicates."""
    ids = sorted(set(user_ids))
    pool = list(ROLE_ART.get(role, ()))
    if not ids or not pool:
        return {}
    if len(ids) > len(pool):
        raise ValueError(f"Not enough private art for role: {role}")

    seed_bytes = hashlib.sha256(f"role-art:{role}:{game_id}".encode()).digest()[:8]
    rng = random.Random(int.from_bytes(seed_bytes, "big"))
    rng.shuffle(pool)
    return {user_id: pool[index] for index, user_id in enumerate(ids)}


def bandit_art_assignments(game_id: int, user_ids: Sequence[int]) -> dict[int, PrivateRoleArt]:
    """Backward-compatible helper used by older tests/integrations."""
    return role_art_assignments(game_id, "mafia", user_ids)


def load_private_role_art(art: PrivateRoleArt, *, root: Path = PRIVATE_ART_ROOT) -> bytes:
    """Load one authored JPEG from small base64 text chunks in the repository."""
    asset_dir = root / art.role / art.asset_key
    parts = sorted(asset_dir.glob("*.part"))
    if not parts:
        raise FileNotFoundError(f"Private role art is missing: {art.role}/{art.asset_key}")
    encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    payload = base64.b64decode(encoded, validate=True)
    if not payload.startswith(b"\xff\xd8"):
        raise ValueError(f"Private role art is not a JPEG: {art.role}/{art.asset_key}")
    return payload
