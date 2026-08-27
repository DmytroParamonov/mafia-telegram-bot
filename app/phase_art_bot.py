from __future__ import annotations

from typing import Any

from aiogram.methods import SendMessage
from aiogram.types import FSInputFile, InlineKeyboardMarkup

from app.phase_art import phase_art_kind_for_text, phase_art_path
from app.stalker_theme import StalkerBot, stalkerize_text


KAIMANOV_REPLACEMENTS = (
    ("Польовий медик", "Лікар"),
    ("ПОЛЬОВИЙ МЕДИК", "ЛІКАР"),
    ("польовий медик", "лікар"),
    ("💉 Медик", "💉 Лікар"),
    ("Медик", "Лікар"),
    ("медик", "лікар"),
)


def kaimanovize_text(text: str) -> str:
    """Keep Kaimanov as the character name while presenting the role as Лікар."""
    for source, target in KAIMANOV_REPLACEMENTS:
        text = text.replace(source, target)
    return text


def kaimanovize_markup(markup: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    """Normalize doctor-role wording on inline buttons too."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                button.model_copy(update={"text": kaimanovize_text(button.text)})
                for button in row
            ]
            for row in markup.inline_keyboard
        ]
    )


class PhaseArtStalkerBot(StalkerBot):
    """STALKER bot with local day/night group art and current role wording."""

    async def __call__(
        self,
        method: Any,
        request_timeout: int | None = None,
    ) -> Any:
        # Message.answer()/query.message.answer() create SendMessage methods
        # directly, bypassing Bot.send_message(). Intercept them here too so
        # /test can preview the same day/night art without a real 5-player game.
        if isinstance(method, SendMessage):
            styled = kaimanovize_text(stalkerize_text(method.text))
            kind = phase_art_kind_for_text(styled)
            image = phase_art_path(kind) if kind is not None else None
            if image is not None and len(styled) <= 1000:
                photo_kwargs: dict[str, Any] = {}
                for field in (
                    "message_thread_id",
                    "disable_notification",
                    "protect_content",
                    "reply_parameters",
                    "reply_markup",
                ):
                    value = getattr(method, field, None)
                    if value is not None:
                        if field == "reply_markup" and isinstance(value, InlineKeyboardMarkup):
                            value = kaimanovize_markup(value)
                        photo_kwargs[field] = value
                return await self.send_photo(
                    chat_id=method.chat_id,
                    photo=FSInputFile(image),
                    caption=styled,
                    **photo_kwargs,
                )

        updates: dict[str, Any] = {}
        for field in ("text", "caption"):
            value = getattr(method, field, None)
            if isinstance(value, str):
                updates[field] = kaimanovize_text(value)

        reply_markup = getattr(method, "reply_markup", None)
        if isinstance(reply_markup, InlineKeyboardMarkup):
            updates["reply_markup"] = kaimanovize_markup(reply_markup)

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
            if isinstance(photo_kwargs.get("reply_markup"), InlineKeyboardMarkup):
                photo_kwargs["reply_markup"] = kaimanovize_markup(photo_kwargs["reply_markup"])
            return await super().send_photo(
                chat_id=chat_id,
                photo=FSInputFile(image),
                caption=styled,
                **photo_kwargs,
            )

        return await super().send_message(chat_id=chat_id, text=text, **kwargs)
