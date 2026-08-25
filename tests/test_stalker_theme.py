from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.stalker_theme import stalkerize_markup, stalkerize_text


def test_lobby_text_is_rethemed() -> None:
    source = (
        "🎭 <b>Новая игра в Мафию</b>\n\n"
        "👑 Хост: <b>Dima</b>\n"
        "👑 Дон: ✅\n"
        "🕵️ Комиссар: ✅\n"
        "🩺 Доктор: ✅"
    )
    themed = stalkerize_text(source)
    assert "НОВА ХОДКА В ЗОНУ" in themed
    assert "Старший групи" in themed
    assert "Авторитет" in themed
    assert "Розвідник" in themed
    assert "Польовий медик" in themed


def test_night_text_is_rethemed() -> None:
    themed = stalkerize_text(
        "🌙 <b>Ночь 1</b>\n\n"
        "Город засыпает. Игроки с ночными ролями получили действия в личке."
    )
    assert "Ніч у Зоні" in themed
    assert "дозиметр" in themed


def test_role_card_is_rethemed() -> None:
    themed = stalkerize_text(
        "🎭 <b>Твоя роль: 🔫 Мафия</b>\n\n"
        "Ночью вместе с мафией выбирай жертву. Днём не выдай себя."
    )
    assert "ПДА: твоя роль" in themed
    assert "Бандит" in themed
    assert "бандитської братви" in themed


def test_inline_buttons_are_rethemed_without_touching_callback_data() -> None:
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Игроки набраны", callback_data="l:start:42")],
            [InlineKeyboardButton(text="👑 Дон ✅", callback_data="l:toggle_don:42")],
        ]
    )
    themed = stalkerize_markup(markup)
    assert themed.inline_keyboard[0][0].text == "🚪 Вирушаємо"
    assert themed.inline_keyboard[0][0].callback_data == "l:start:42"
    assert themed.inline_keyboard[1][0].text == "👑 Авторитет ✅"
    assert themed.inline_keyboard[1][0].callback_data == "l:toggle_don:42"
