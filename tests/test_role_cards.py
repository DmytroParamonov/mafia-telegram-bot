from pathlib import Path

from app.role_cards import build_ready_role_card, ready_role_card_path


def test_ready_role_card_is_jpeg() -> None:
    payload = build_ready_role_card(role="bloodsucker", callsign="Туман")
    assert payload.startswith(b"\xff\xd8")
    assert len(payload) > 10_000


def test_ready_card_path_is_stable() -> None:
    path = ready_role_card_path("mafia", "Бугор", root=Path("cards"))
    assert path == Path("cards/mafia/01.jpg")
