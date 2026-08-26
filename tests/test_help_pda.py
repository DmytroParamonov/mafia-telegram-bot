from app.game.rules import Role
from app.help_content import HELP_SECTIONS, role_help_text
from app.keyboards import help_keyboard, lobby_keyboard, role_card_help_keyboard
from app.models import Game


def test_lobby_has_private_rules_button() -> None:
    game = Game(id=7, chat_id=-100, host_user_id=1)
    markup = lobby_keyboard(game, "https://t.me/test_bot?start=join_7")
    buttons = [button for row in markup.inline_keyboard for button in row]
    rules = next(button for button in buttons if button.text == "📖 Правила")
    assert rules.url == "https://t.me/test_bot?start=rules"


def test_help_menu_contains_main_sections() -> None:
    markup = help_keyboard()
    callbacks = {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }
    assert {
        "help:game",
        "help:roles",
        "help:win",
        "help:night",
        "help:vote",
        "help:dead",
        "help:zone",
        "help:timers",
        "help:commands",
    } <= callbacks
    assert set(HELP_SECTIONS) == {
        "game",
        "roles",
        "win",
        "night",
        "vote",
        "dead",
        "zone",
        "timers",
        "commands",
    }


def test_role_card_has_contextual_help_button() -> None:
    markup = role_card_help_keyboard(42)
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    ]
    assert "pda:role:42" in callbacks
    assert "help:menu" in callbacks


def test_every_active_role_has_private_explanation() -> None:
    for role in (
        Role.CIVILIAN.value,
        Role.MAFIA.value,
        Role.SHERIFF.value,
        Role.DOCTOR.value,
        Role.BLOODSUCKER.value,
    ):
        text = role_help_text(role)
        assert text is not None
        assert "ТВОЯ РОЛЬ" in text
