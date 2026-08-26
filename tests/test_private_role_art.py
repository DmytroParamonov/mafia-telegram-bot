from pathlib import Path

from app.game.rules import Role
from app.private_role_art import (
    ROLE_ART,
    ensure_private_role_art_dirs,
    load_private_role_art,
    private_role_art_path,
    role_art_assignments,
)


def test_role_art_assignments_are_stable_and_unique() -> None:
    user_ids = [30, 10]
    first = role_art_assignments(77, Role.MAFIA.value, user_ids)
    second = role_art_assignments(77, Role.MAFIA.value, list(reversed(user_ids)))

    assert first == second
    assert set(first) == {10, 30}
    assert len({art.asset_key for art in first.values()}) == 2


def test_full_private_art_catalog_matches_playtest_pack() -> None:
    assert [art.internal_name for art in ROLE_ART[Role.MAFIA.value]] == [
        "Саня Кабан",
        "Гоша Кекс",
        "Гриша Музарука",
        "Жека Гнилий",
        "Толік Барсук",
    ]
    assert len(ROLE_ART[Role.CIVILIAN.value]) == 10
    assert len(ROLE_ART[Role.DOCTOR.value]) == 1
    assert len(ROLE_ART[Role.SHERIFF.value]) == 1
    assert len(ROLE_ART[Role.BLOODSUCKER.value]) == 1
    assert sum(len(items) for items in ROLE_ART.values()) == 18


def test_local_art_folders_and_loading(tmp_path: Path) -> None:
    ensure_private_role_art_dirs(root=tmp_path)
    for role in ROLE_ART:
        assert (tmp_path / role).is_dir()

    art = ROLE_ART[Role.MAFIA.value][0]
    image_path = tmp_path / Role.MAFIA.value / "01.jpg"
    image_path.write_bytes(b"\xff\xd8fake-jpeg")

    assert private_role_art_path(art, root=tmp_path) == image_path
    assert load_private_role_art(art, root=tmp_path) == b"\xff\xd8fake-jpeg"
