from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    CIVILIAN = "civilian"
    MAFIA = "mafia"
    DON = "don"
    SHERIFF = "sheriff"
    DOCTOR = "doctor"


MAFIA_ROLES = {Role.MAFIA.value, Role.DON.value}

ROLE_TITLES = {
    Role.CIVILIAN.value: "🧑 Мирный житель",
    Role.MAFIA.value: "🔫 Мафия",
    Role.DON.value: "👑 Дон",
    Role.SHERIFF.value: "🕵️ Комиссар",
    Role.DOCTOR.value: "🩺 Доктор",
}

ROLE_DESCRIPTIONS = {
    Role.CIVILIAN.value: "Найди мафию и помоги городу изгнать преступников.",
    Role.MAFIA.value: "Ночью вместе с мафией выбирай жертву. Днём не выдай себя.",
    Role.DON.value: "Ты глава мафии. Участвуешь в убийстве и ночью ищешь Комиссара.",
    Role.SHERIFF.value: "Каждую ночь проверяй одного игрока: мафия он или нет.",
    Role.DOCTOR.value: "Каждую ночь лечи одного живого игрока, включая себя.",
}


@dataclass(frozen=True, slots=True)
class RoleSetup:
    enable_don: bool = True
    enable_sheriff: bool = True
    enable_doctor: bool = True


def mafia_team_size(player_count: int) -> int:
    """Balanced mafia-team size for 5–20 players."""
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
    return "mafia" if role in MAFIA_ROLES else "city"


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
