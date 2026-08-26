from app.private_role_art import BANDIT_ART, bandit_art_assignments, load_private_role_art


def test_bandit_art_assignments_are_stable_and_unique() -> None:
    user_ids = [30, 10]
    first = bandit_art_assignments(77, user_ids)
    second = bandit_art_assignments(77, list(reversed(user_ids)))

    assert first == second
    assert set(first) == {10, 30}
    assert len({art.asset_key for art in first.values()}) == 2


def test_all_five_authored_bandit_assets_decode_as_jpeg() -> None:
    assert [art.internal_name for art in BANDIT_ART] == [
        "Саня Кабан",
        "Гоша Кекс",
        "Вітя Шрам",
        "Жека Гнилий",
        "Толік Барсук",
    ]
    assert len(BANDIT_ART) == 5

    for art in BANDIT_ART:
        payload = load_private_role_art(art)
        assert payload.startswith(b"\xff\xd8")
        assert len(payload) > 1_000
