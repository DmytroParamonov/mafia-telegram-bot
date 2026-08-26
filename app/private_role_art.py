from __future__ import annotations

import base64
import hashlib
import random
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Sequence


PRIVATE_ART_ROOT = Path("assets/private_role_art")


@dataclass(frozen=True, slots=True)
class PrivateRoleArt:
    internal_name: str
    asset_key: str


# Internal bookkeeping only. These names are never shown publicly and do not
# replace a player's public callsign. The authored picture is visible only in
# that player's private PDA.
BANDIT_ART: tuple[PrivateRoleArt, ...] = (
    PrivateRoleArt("Саня Кабан", "sanya_kaban"),
    PrivateRoleArt("Гоша Кекс", "gosha_keks"),
    PrivateRoleArt("Вітя Шрам", "vitya_shram"),
    PrivateRoleArt("Жека Гнилий", "zheka_gniliy"),
    PrivateRoleArt("Толік Барсук", "tolik_barsuk"),
)


def bandit_art_assignments(game_id: int, user_ids: Sequence[int]) -> dict[int, PrivateRoleArt]:
    """Assign distinct authored bandit portraits deterministically for one game."""
    ids = sorted(set(user_ids))
    if len(ids) > len(BANDIT_ART):
        raise ValueError("Not enough private bandit art for this game")

    seed_bytes = hashlib.sha256(f"bandit-art:{game_id}".encode()).digest()[:8]
    rng = random.Random(int.from_bytes(seed_bytes, "big"))
    pool = list(BANDIT_ART)
    rng.shuffle(pool)
    return {user_id: pool[index] for index, user_id in enumerate(ids)}


def _asset_parts(art: PrivateRoleArt, *, root: Path = PRIVATE_ART_ROOT) -> list[Path]:
    return sorted((root / "bandit").glob(f"{art.asset_key}.*.part"))


def load_private_role_art(art: PrivateRoleArt, *, root: Path = PRIVATE_ART_ROOT) -> bytes:
    """Load an authored JPEG stored as small base64 text chunks in the repository."""
    parts = _asset_parts(art, root=root)
    if not parts:
        raise FileNotFoundError(f"Private role art is missing: {art.asset_key}")
    encoded = "".join(part.read_text(encoding="ascii").strip() for part in parts)
    payload = base64.b64decode(encoded, validate=True)
    if not payload.startswith(b"\xff\xd8"):
        raise ValueError(f"Private role art is not a JPEG: {art.asset_key}")
    return payload
