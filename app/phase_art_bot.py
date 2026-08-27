from __future__ import annotations

from typing import Any

from aiogram.types import FSInputFile

from app.phase_art import phase_art_kind_for_text, phase_art_path
from app.stalker_theme import StalkerBot, stalkerize_text


KAIMANOV_REPLACEMENTS = (
    ("Польовий медик", "Доктор Кайманов"),
    ("ПОЛЬОВИЙ МЕДИК", "ДОКТОР КАЙМАНОВ"),
    ("польовий медик", "Доктор Кайманов"),
)


def kaimanovize_text(text: str) -> str:
    for source, target in KAIMANOV_REPLACEMENTS:
        text = text.replace(source, target)
    return text


class PhaseArtStalkerBot(StalkerBot):
    """STALKER bot with local day/night group art and Kaimanov naming."""

    async def __call__(
        self,
        method: Any,
        request_timeout: int | None = None,
    ) -> Any:
        updates: dict[str, Any] = {}
        for field in ("text", "caption"):
            value = getattr(method, field, None)
            if isinstance(value, str):
                updates[field] = kaimanovize_text(value)

        if updates and hasattr(method, "model_copy"):
            method = method.model_copy(update=updates)

        return await super().__call__(method, request_timeout=request_timeout)

    async def send_message(self, chat_id: int | str, text: str, **kwargs: Any) -> Any:
        """Use a local day/night picture as the visual shell for major public phases."""
        styled = kaimanovize_text(stalkerize_text(text))
        kind = phase_art_kind_for_text(styled)
        image = phase_art_path(kind) if kind is not None else None

        # Telegram photo captions are limited to 1024 characters. Major phase
        # announcements are normally shorter, but fall back to a plain message
        # rather than truncate anything if a roster ever becomes too long.
        if image is not None and len(styled) <= 1000:
            photo_kwargs = {
                key: kwargs[key]
                for key in (
                    "message_thread_id",
                    "disable_notification",
                    "protect_content",
                    "reply_parameters",
                    "reply_markup",
                )
                if key in kwargs
            }
            return await super().send_photo(
                chat_id=chat_id,
                photo=FSInputFile(image),
                caption=styled,
                **photo_kwargs,
            )

        return await super().send_message(chat_id=chat_id, text=text, **kwargs)
