from datetime import UTC, datetime

import pytest
from aiogram.types import Chat, Message, User

from app.zone_handlers import private_pda_text, router


def _private_message(text: str) -> Message:
    return Message(
        message_id=1,
        date=datetime.now(UTC),
        chat=Chat(id=123, type="private"),
        from_user=User(id=456, is_bot=False, first_name="Test"),
        text=text,
    )


@pytest.mark.asyncio
async def test_private_pda_text_does_not_swallow_slash_commands() -> None:
    observer = router.observers["message"]
    handler = next(item for item in observer.handlers if item.callback is private_pda_text)

    command_match, _ = await handler.check(_private_message("/help"))
    text_match, _ = await handler.check(_private_message("повідомлення братві"))

    assert command_match is False
    assert text_match is True
