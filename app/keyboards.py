from __future__ import annotations

from collections.abc import Iterable, Mapping

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.models import Game, GamePlayer


def yn(value: bool) -> str:
    return "✅" if value else "❌"


def _rules_url(join_url: str) -> str:
    base = join_url.split("?start=", 1)[0]
    return f"{base}?start=rules"


def lobby_keyboard(game: Game, join_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔥 Сісти до багаття", url=join_url),
                InlineKeyboardButton(text="📖 Правила", url=_rules_url(join_url)),
            ],
            [
                InlineKeyboardButton(text="🚶 Відійти", callback_data=f"l:leave:{game.id}"),
                InlineKeyboardButton(text="🚪 Вирушаємо", callback_data=f"l:start:{game.id}"),
            ],
            [
                InlineKeyboardButton(
                    text=f"☢️ Жива Зона {yn(game.live_zone)}",
                    callback_data=f"l:toggle_live_zone:{game.id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"🧛 Кровосос {yn(game.enable_don)}",
                    callback_data=f"l:toggle_don:{game.id}",
                ),
                InlineKeyboardButton(
                    text=f"☠️ Ролі вибулих {yn(game.reveal_roles)}",
                    callback_data=f"l:toggle_reveal:{game.id}",
                ),
            ],
            [InlineKeyboardButton(text="❌ Розпустити групу", callback_data=f"l:cancel:{game.id}")],
        ]
    )


def help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎮 Як грати", callback_data="help:game"),
                InlineKeyboardButton(text="🎭 Ролі", callback_data="help:roles"),
            ],
            [
                InlineKeyboardButton(text="🏆 Перемога", callback_data="help:win"),
                InlineKeyboardButton(text="🌘 Ніч", callback_data="help:night"),
            ],
            [
                InlineKeyboardButton(text="🗳 Голосування", callback_data="help:vote"),
                InlineKeyboardButton(text="☠️ Після смерті", callback_data="help:dead"),
            ],
            [
                InlineKeyboardButton(text="☢️ Режими Зони", callback_data="help:zone"),
                InlineKeyboardButton(text="⏱ Таймери", callback_data="help:timers"),
            ],
            [InlineKeyboardButton(text="🤖 Команди", callback_data="help:commands")],
        ]
    )


def help_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ До довідника", callback_data="help:menu")]]
    )


def role_card_help_keyboard(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❓ Що робить моя роль?", callback_data=f"pda:role:{game_id}")],
            [InlineKeyboardButton(text="📖 Правила гри", callback_data="help:menu")],
        ]
    )


def _label(player: GamePlayer, labels: Mapping[int, str] | None) -> str:
    if labels is None:
        return player.display_name
    return labels.get(player.user_id, player.display_name)


def target_keyboard(
    *,
    game_id: int,
    day_number: int,
    action_code: str,
    players: Iterable[GamePlayer],
    labels: Mapping[int, str] | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_label(player, labels),
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
    labels: Mapping[int, str] | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=_label(player, labels),
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
                    text="⏭ Завершити етап",
                    callback_data=f"h:advance:{game.id}:{token}",
                ),
                InlineKeyboardButton(
                    text="➕ +60 сек.",
                    callback_data=f"h:extend:{game.id}:{token}",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🛑 Завершити ходку",
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
                    text="🛑 Так, завершуємо",
                    callback_data=f"h:confirm_end:{game.id}:{token}",
                )
            ],
            [InlineKeyboardButton(text="↩️ Ні", callback_data=f"h:dismiss:{game.id}")],
        ]
    )


def rematch_keyboard(game_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Ще одна ходка",
                    callback_data=f"h:rematch:{game_id}",
                )
            ]
        ]
    )
