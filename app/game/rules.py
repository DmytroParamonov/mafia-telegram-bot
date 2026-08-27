from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    CIVILIAN = "civilian"
    MAFIA = "mafia"
    DON = "don"  # legacy role kept for old games/database compatibility
    SHERIFF = "sheriff"
    DOCTOR = "doctor"
    BLOODSUCKER = "bloodsucker"


MAFIA_ROLES = {Role.MAFIA.value, Role.DON.value}
HOSTILE_ROLES = {*MAFIA_ROLES, Role.BLOODSUCKER.value}

ROLE_TITLES = {
    Role.CIVILIAN.value: "☢️ Вільний сталкер",
    Role.MAFIA.value: "🔪 Бандит",
    Role.DON.value: "👑 Авторитет",
    Role.SHERIFF.value: "🔎 Розвідник",
    Role.DOCTOR.value: "💉 Лікар",
    Role.BLOODSUCKER.value: "🧛 Кровосос",
}

ROLE_DESCRIPTIONS = {
    Role.CIVILIAN.value: "На сходці вирахуй загрози раніше, ніж вони переб'ють табір.",
    Role.MAFIA.value: "Уночі домовся з братвою про одну ціль. Якщо голоси розійдуться — наліт зірветься.",
    Role.DON.value: "Застаріла роль для сумісності зі старими партіями.",
    Role.SHERIFF.value: "Щоночі перевіряй одного учасника й дізнавайся, чи становить він загрозу табору.",
    Role.DOCTOR.value: "Щоночі рятуй одного живого учасника, включно із собою.",
    Role.BLOODSUCKER.value: "Ти третя сторона. Щоночі полюй на будь-кого й залишся останнім живим.",
}

ROLE_FACTIONS = {
    Role.CIVILIAN.value: "Сталкери",
    Role.MAFIA.value: "Бандити",
    Role.DON.value: "Бандити",
    Role.SHERIFF.value: "Сталкери",
    Role.DOCTOR.value: "Сталкери",
    Role.BLOODSUCKER.value: "Сам за себе",
}


@dataclass(frozen=True, slots=True)
class RoleSetup:
    enable_don: bool = True
    enable_sheriff: bool = True
    enable_doctor: bool = True


# Exact playtest-v2 balance. Bloodsucker is enabled only for 9-10 players.
# Values are: mafia, sheriff, doctor, bloodsucker, civilians.
ZONE_ROLE_COUNTS: dict[int, tuple[int, int, int, int, int]] = {
    5: (1, 1, 0, 0, 3),
    6: (1, 1, 1, 0, 3),
    7: (2, 1, 1, 0, 3),
    8: (2, 1, 1, 0, 4),
    9: (2, 1, 1, 1, 4),
    10: (2, 1, 1, 1, 5),
}


def zone_role_counts(player_count: int, *, enable_bloodsucker: bool = True) -> Counter[str]:
    if player_count not in ZONE_ROLE_COUNTS:
        raise ValueError("Zone mode supports exactly 5-10 players")

    mafia, sheriff, doctor, bloodsucker, civilians = ZONE_ROLE_COUNTS[player_count]
    counts: Counter[str] = Counter(
        {
            Role.MAFIA.value: mafia,
            Role.SHERIFF.value: sheriff,
            Role.DOCTOR.value: doctor,
            Role.BLOODSUCKER.value: bloodsucker if enable_bloodsucker else 0,
            Role.CIVILIAN.value: civilians,
        }
    )
    if not enable_bloodsucker and bloodsucker:
        counts[Role.CIVILIAN.value] += bloodsucker
    return counts


def build_zone_roles(
    player_count: int,
    *,
    enable_bloodsucker: bool = True,
    rng: random.Random | None = None,
) -> list[str]:
    counts = zone_role_counts(player_count, enable_bloodsucker=enable_bloodsucker)
    roles: list[str] = []
    for role in (
        Role.MAFIA.value,
        Role.SHERIFF.value,
        Role.DOCTOR.value,
        Role.BLOODSUCKER.value,
        Role.CIVILIAN.value,
    ):
        roles.extend([role] * counts[role])
    (rng or random.SystemRandom()).shuffle(roles)
    return roles


def zone_winner_for_alive_roles(roles: list[str]) -> str | None:
    mafia = sum(1 for role in roles if role in MAFIA_ROLES)
    bloodsuckers = sum(1 for role in roles if role == Role.BLOODSUCKER.value)
    stalkers = len(roles) - mafia - bloodsuckers

    if bloodsuckers:
        if len(roles) == bloodsuckers:
            return "bloodsucker"
        return None

    if mafia == 0:
        return "city"
    if mafia >= stalkers:
        return "mafia"
    return None


def mafia_team_size(player_count: int) -> int:
    """Legacy classic-Mafia balance for old tests/games."""
    if player_count <= 6:
        return 1
    if player_count <= 8:
        return 2
    if player_count <= 11:
        return 3
    if player_count <= 14:
        return 4
    if player_count <= 17:
        return 5
    return 6


def build_roles(player_count: int, setup: RoleSetup, rng: random.Random | None = None) -> list[str]:
    """Legacy classic role builder kept for compatibility."""
    if player_count < 5:
        raise ValueError("At least 5 players are required")
    if player_count > 20:
        raise ValueError("At most 20 players are supported")

    mafia_count = mafia_team_size(player_count)
    roles: list[str] = []

    if setup.enable_don and player_count >= 7 and mafia_count >= 2:
        roles.append(Role.DON.value)
        mafia_count -= 1

    roles.extend([Role.MAFIA.value] * mafia_count)

    if setup.enable_sheriff:
        roles.append(Role.SHERIFF.value)
    if setup.enable_doctor and player_count >= 6:
        roles.append(Role.DOCTOR.value)

    if len(roles) > player_count:
        raise ValueError("Too many enabled special roles")

    roles.extend([Role.CIVILIAN.value] * (player_count - len(roles)))
    (rng or random.SystemRandom()).shuffle(roles)
    return roles


def team_for_role(role: str | None) -> str:
    if role in MAFIA_ROLES:
        return "mafia"
    if role == Role.BLOODSUCKER.value:
        return "bloodsucker"
    return "city"


def winner_for_alive_roles(roles: list[str]) -> str | None:
    mafia = sum(1 for role in roles if role in MAFIA_ROLES)
    city = len(roles) - mafia
    if mafia == 0:
        return "city"
    if mafia >= city:
        return "mafia"
    return None


def unique_vote_winner(target_ids: list[int]) -> tuple[int | None, list[int]]:
    """Return unique winner or tied leaders. Empty input returns no winner/no leaders."""
    if not target_ids:
        return None, []
    counts = Counter(target_ids)
    top_count = max(counts.values())
    leaders = sorted(target for target, count in counts.items() if count == top_count)
    if len(leaders) == 1:
        return leaders[0], leaders
    return None, leaders
