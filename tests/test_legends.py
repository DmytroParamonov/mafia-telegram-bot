from app.legends import LEGENDS, legend_assignments


def test_legend_pool_has_100_unique_entries() -> None:
    assert len(LEGENDS) == 100
    assert len({legend.number for legend in LEGENDS}) == 100


def test_legends_are_distinct_inside_one_game_and_stable() -> None:
    players = list(range(1, 11))
    first = legend_assignments(77, players)
    second = legend_assignments(77, players)

    assert first == second
    assert len({legend.number for legend in first.values()}) == len(players)


def test_next_game_reshuffles_legends() -> None:
    players = list(range(1, 11))
    first = legend_assignments(77, players)
    second = legend_assignments(78, players)

    assert [first[player].number for player in players] != [second[player].number for player in players]
