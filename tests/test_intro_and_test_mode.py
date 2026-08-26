from app.config import Settings
from app.playtest_service import PlaytestGameService
from app.test_mode import test_menu


def test_playtest_discussion_is_three_minutes() -> None:
    settings = Settings(BOT_TOKEN="123:abc", DISCUSSION_SECONDS=240)
    service = PlaytestGameService(
        bot=None,
        session_factory=None,
        bot_username="test_bot",
        settings=settings,
    )
    assert service.settings.discussion_seconds == 180


def test_test_menu_contains_preview_tools() -> None:
    markup = test_menu()
    callbacks = {
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data
    }
    assert {"t:cards", "t:flow", "t:night", "t:event", "t:death", "t:morning"} <= callbacks
