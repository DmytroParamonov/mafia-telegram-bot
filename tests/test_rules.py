import random

import pytest

from app.game.rules import (
    MAFIA_ROLES,
    Role,
    RoleSetup,
    build_roles,
    mafia_team_size,
    unique_vote_winner,
    winner_for_alive_roles,
)


@pytest.mark.parametrize(
    ("players", "mafia"),
    [(5, 1), (6, 1), (7, 2), (8, 2), (9, 3), (11, 3), (12, 4), (15, 5), (20, 6)],
)
def test_mafia_team_size(players: int, mafia: int) -> None:
    assert mafia_team_size(players) == mafia


def test_build_roles_for_seven_players() -> None:
    roles = build_roles(7, RoleSetup(), random.Random(42))
    assert len(roles) == 7
    assert sum(role in MAFIA_ROLES for role in roles) == 2
    assert Role.DON.value in roles
    assert Role.SHERIFF.value in roles
    assert Role.DOCTOR.value in roles


def test_disabled_special_roles_are_not_added() -> None:
    roles = build_roles(
        10,
        RoleSetup(enable_don=False, enable_sheriff=False, enable_doctor=False),
        random.Random(1),
    )
    assert Role.DON.value not in roles
    assert Role.SHERIFF.value not in roles
    assert Role.DOCTOR.value not in roles
    assert sum(role in MAFIA_ROLES for role in roles) == 3


def test_city_wins_when_mafia_is_gone() -> None:
    assert winner_for_alive_roles([Role.CIVILIAN.value, Role.SHERIFF.value]) == "city"


def test_mafia_wins_at_parity() -> None:
    assert winner_for_alive_roles([Role.MAFIA.value, Role.CIVILIAN.value]) == "mafia"


def test_game_continues_before_parity() -> None:
    assert (
        winner_for_alive_roles(
            [Role.MAFIA.value, Role.CIVILIAN.value, Role.CIVILIAN.value]
        )
        is None
    )


def test_unique_vote_winner() -> None:
    winner, leaders = unique_vote_winner([1, 1, 2, 3])
    assert winner == 1
    assert leaders == [1]


def test_vote_tie_returns_leaders() -> None:
    winner, leaders = unique_vote_winner([1, 1, 2, 2, 3])
    assert winner is None
    assert leaders == [1, 2]


def test_empty_vote() -> None:
    assert unique_vote_winner([]) == (None, [])
