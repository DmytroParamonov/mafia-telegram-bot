from collections import Counter

import pytest

from app.game.rules import Role, build_zone_roles, zone_role_counts, zone_winner_for_alive_roles


EXPECTED = {
    5: {"mafia": 1, "sheriff": 1, "doctor": 0, "bloodsucker": 0, "civilian": 3},
    6: {"mafia": 1, "sheriff": 1, "doctor": 1, "bloodsucker": 0, "civilian": 3},
    7: {"mafia": 2, "sheriff": 1, "doctor": 1, "bloodsucker": 0, "civilian": 3},
    8: {"mafia": 2, "sheriff": 1, "doctor": 1, "bloodsucker": 0, "civilian": 4},
    9: {"mafia": 2, "sheriff": 1, "doctor": 1, "bloodsucker": 1, "civilian": 4},
    10: {"mafia": 2, "sheriff": 1, "doctor": 1, "bloodsucker": 1, "civilian": 5},
}


@pytest.mark.parametrize("player_count", range(5, 11))
def test_exact_zone_balance(player_count: int) -> None:
    counts = zone_role_counts(player_count)
    assert sum(counts.values()) == player_count
    for role, expected_count in EXPECTED[player_count].items():
        assert counts[role] == expected_count


def test_disabling_bloodsucker_turns_it_into_civilian() -> None:
    counts = zone_role_counts(10, enable_bloodsucker=False)
    assert counts[Role.BLOODSUCKER.value] == 0
    assert counts[Role.CIVILIAN.value] == 6


def test_build_zone_roles_matches_counts() -> None:
    roles = build_zone_roles(10)
    assert Counter(roles) == zone_role_counts(10)


def test_zone_win_conditions_have_three_sides() -> None:
    assert zone_winner_for_alive_roles([Role.CIVILIAN.value, Role.SHERIFF.value]) == "city"
    assert zone_winner_for_alive_roles([Role.MAFIA.value, Role.CIVILIAN.value]) == "mafia"
    assert zone_winner_for_alive_roles([Role.BLOODSUCKER.value]) == "bloodsucker"

    # No early win while the third side is alive.
    assert zone_winner_for_alive_roles([Role.MAFIA.value, Role.BLOODSUCKER.value]) is None
    assert zone_winner_for_alive_roles([Role.CIVILIAN.value, Role.BLOODSUCKER.value]) is None
