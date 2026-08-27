from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from app.game.rules import Role


PRIVATE_ART_ROOT = Path("data/private_role_art")
SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


@dataclass(frozen=True, slots=True)
class PrivateRoleArt:
    role: str
    internal_name: str
    asset_key: str


# The images themselves are intentionally NOT stored in GitHub.  Only this
# catalog and empty folders live in the repository.  On the bot host, drop the
# authored images into data/private_role_art/<role>/ using the numeric names.
ROLE_ART: dict[str, tuple[PrivateRoleArt, ...]] = {
    Role.MAFIA.value: (
        PrivateRoleArt(Role.MAFIA.value, "Саня Кабан", "01"),
        PrivateRoleArt(Role.MAFIA.value, "Гоша Кекс", "02"),
        PrivateRoleArt(Role.MAFIA.value, "Гриша Музарука", "03"),
        PrivateRoleArt(Role.MAFIA.value, "Жека Гнилий", "04"),
        PrivateRoleArt(Role.MAFIA.value, "Толік Барсук", "05"),
    ),
    Role.CIVILIAN.value: (
        PrivateRoleArt(Role.CIVILIAN.value, "Серьога Ворон", "01"),
        PrivateRoleArt(Role.CIVILIAN.value, "Коля Тихий", "02"),
        PrivateRoleArt(Role.CIVILIAN.value, "Вадік Рижий", "03"),
        PrivateRoleArt(Role.CIVILIAN.value, "Паша Борода", "04"),
        PrivateRoleArt(Role.CIVILIAN.value, "Діма Філін", "05"),
        PrivateRoleArt(Role.CIVILIAN.value, "Ігор Крот", "06"),
        PrivateRoleArt(Role.CIVILIAN.value, "Вова Сєдой", "07"),
        PrivateRoleArt(Role.CIVILIAN.value, "Рома Яструб", "08"),
        PrivateRoleArt(Role.CIVILIAN.value, "Макс Монах", "09"),
        PrivateRoleArt(Role.CIVILIAN.value, "Льоха Кузнєц", "10"),
    ),
    Role.DOCTOR.value: (
        PrivateRoleArt(Role.DOCTOR.value, "Доктор Кайманов", "01"),
    ),
    Role.SHERIFF.value: (
        PrivateRoleArt(Role.SHERIFF.value, "Розвідник", "01"),
    ),
    Role.BLOODSUCKER.value: (
        PrivateRoleArt(Role.BLOODSUCKER.value, "Кровосос", "01"),
    ),
}


def ensure_private_role_art_dirs(*, root: Path = PRIVATE_ART_ROOT) -> None:
    """Create the local folders expected by the bot if they are missing."""
    for role in ROLE_ART:
        (root / role).mkdir(parents=True, exist_ok=True)


def role_art_assignments(
    game_id: int,
    role: str,
    user_ids: Sequence[int],
) -> dict[int, PrivateRoleArt]:
    """Assign distinct authored portraits deterministically within one role."""
    ids = sorted(set(user_ids))
    pool = ROLE_ART.get(role, ())
    if not ids or not pool:
        return {}
    if len(ids) > len(pool):
        raise ValueError(f"Not enough private art for role {role}")

    seed_bytes = hashlib.sha256(f"private-art:{game_id}:{role}".encode()).digest()[:8]
    rng = random.Random(int.from_bytes(seed_bytes, "big"))
    shuffled = list(pool)
    rng.shuffle(shuffled)
    return {user_id: shuffled[index] for index, user_id in enumerate(ids)}


def private_role_art_path(
    art: PrivateRoleArt,
    *,
    root: Path = PRIVATE_ART_ROOT,
) -> Path | None:
    """Return the first local image matching an authored-art slot."""
    folder = root / art.role
    for extension in SUPPORTED_EXTENSIONS:
        candidate = folder / f"{art.asset_key}{extension}"
        if candidate.is_file():
            return candidate
    return None


def load_private_role_art(
    art: PrivateRoleArt,
    *,
    root: Path = PRIVATE_ART_ROOT,
) -> bytes:
    path = private_role_art_path(art, root=root)
    if path is None:
        raise FileNotFoundError(
            f"Private role art is missing: {art.role}/{art.asset_key}"
        )
    payload = path.read_bytes()
    if not payload:
        raise ValueError(f"Private role art is empty: {path}")
    return payload
