from app.role_cards import build_role_card


def test_role_card_is_generated_as_jpeg() -> None:
    payload = build_role_card(
        role="bloodsucker",
        role_title="🧛 Кровосос",
        player_label="№9 «Туман» — Тестер",
        faction="Сам за себе",
        description="Третя сторона. Залишся останнім живим.",
    )
    assert payload.startswith(b"\xff\xd8")
    assert len(payload) > 10_000
