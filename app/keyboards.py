from __future__ import annotations

from collections.abc import Iterable

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import Game, GamePlayer


def yn(value: bool) -> str:
    return "✅" if value else "❌"


def lobby_keyboard(game: Game, join_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Войти в игру", url=join_url),
                InlineKeyboardButton(text="➖ Выйти", callback_data=f"l:leave:{game.id}"),
            ],
            [InlineKeyboardButton(text="🚀 Игроки набраны", callback_data=f"l:start:{game.id}")],
            [
                InlineKeyboardButton(
                    text=f"👑 Дон {yn(game.enable_don)}",
                    callback_data=f"l:toggle_don:{game.id}",
                ),
                InlineKeyboardButton(
                    text=f"🕵️ Комиссар {yn(game.enable_sheriff)}",
                    callback_data=f"l:toggle_sheriff:{game.id}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"🩺 Доктор {yn(game.enable_doctor)}",
                    callback_data=f"l:toggle_doctor:{game.id}",
                ),
                InlineKeyboardButton(
                    text=f"🎭 Роли после смерти {yn(game.reveal_roles)}",
                    callback_data=f"l:toggle_reveal:{game.id}",
                ),
            ],
            [InlineKeyboardButton(text="❌ Отменить лобби", callback_data=f"l:cancel:{game.id}")],
        ]
    )


def target_keyboard(
    *,
    game_id: int,
    day_number: int,
    action_code: str,
    players: Iterable[GamePlayer],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=player.display_name,
                callback_data=f"a:{game_id}:{day_number}:{action_code}:{player.user_id}",
            )
        ]
        for player in players
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def vote_keyboard(
    *,
    game_id: int,
    day_number: int,
    vote_round: int,
    players: Iterable[GamePlayer],
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=player.display_name,
                callback_data=f"v:{game_id}:{day_number}:{vote_round}:{player.user_id}",
            )
        ]
        for player in players
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def host_phase_keyboard(game: Game) -> InlineKeyboardMarkup:
    token = f"{game.day_number}:{game.phase}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⏭ Завершить фазу",
                    callback_data=f"h:advance:{game.id}:{token}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🛑 Завершить игру",
                    callback_data=f"h:end:{game.id}:{token}",
                )
            ],
        ]
    )


def confirm_end_keyboard(game: Game) -> InlineKeyboardMarkup:
    token = f"{game.day_number}:{game.phase}"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛑 Да, завершить",
                    callback_data=f"h:confirm_end:{game.id}:{token}",
                )
            ],
            [InlineKeyboardButton(text="↩️ Нет", callback_data=f"h:dismiss:{game.id}")],
        ]
    )


def rematch_keyboard(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Реванш тем же составом",
                    callback_data=f"h:rematch:{game_id}",
                )
            ]
        ]
    )
