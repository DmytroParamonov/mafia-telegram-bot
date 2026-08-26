from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.game.rules import ROLE_DESCRIPTIONS, ROLE_FACTIONS, ROLE_TITLES, Role
from app.role_cards import build_role_card
from app.zone_features import choose_zone_event, night_death_line, quiet_night_text, saved_text

router = Router()

TEST_ROLES = (
    Role.CIVILIAN.value,
    Role.MAFIA.value,
    Role.SHERIFF.value,
    Role.DOCTOR.value,
    Role.BLOODSUCKER.value,
)


def test_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🎴 Усі картки ролей", callback_data="t:cards")],
            [
                InlineKeyboardButton(text="🔥 Етапи ходки", callback_data="t:flow"),
                InlineKeyboardButton(text="🌘 Нічні ПДА", callback_data="t:night"),
            ],
            [
                InlineKeyboardButton(text="☢️ Подія Зони", callback_data="t:event"),
                InlineKeyboardButton(text="☠️ Смерть", callback_data="t:death"),
            ],
            [InlineKeyboardButton(text="💉 Порятунок / тиха ніч", callback_data="t:morning")],
        ]
    )


def sample_targets() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="№2 «Борода» — Олександр", callback_data="t:noop")],
            [InlineKeyboardButton(text="№3 «Туман» — Вадим", callback_data="t:noop")],
            [InlineKeyboardButton(text="№4 «Ворон» — Лена", callback_data="t:noop")],
        ]
    )


@router.message(Command("test"))
async def test_command(message: Message) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer(
            "🧪 <b>Тестовий полігон працює в особистому ПДА.</b>\n\n"
            "Відкрий особистий чат із ботом і напиши /test. Тут не потрібні 5 гравців і не створюється справжня ходка."
        )
        return

    await message.answer(
        "🧪 <b>ТЕСТОВИЙ ПОЛІГОН ПДА</b>\n\n"
        "Тут можна одному перевіряти вигляд карток, етапів, нічних меню, подій і смертей. "
        "Тест не записується в статистику, не запускає таймери й не потребує інших людей.",
        reply_markup=test_menu(),
    )


@router.callback_query(F.data.startswith("t:"))
async def test_callback(query: CallbackQuery) -> None:
    if query.from_user is None or not query.data:
        return
    action = query.data.split(":", 1)[1]

    if action == "noop":
        await query.answer("🧪 Це тестова кнопка: у справжній ходці тут фіксується вибір.")
        return

    if query.message is None:
        await query.answer()
        return

    await query.answer()

    if action == "cards":
        for index, role in enumerate(TEST_ROLES, start=1):
            label = f"№{index} «Тест-{index}» — Перевірка"
            image = build_role_card(
                role=role,
                role_title=ROLE_TITLES[role],
                player_label=label,
                faction=ROLE_FACTIONS[role],
                description=ROLE_DESCRIPTIONS[role],
            )
            await query.message.answer_photo(
                BufferedInputFile(image, filename=f"test_{role}.jpg"),
                caption=(
                    f"📟 <b>{html.escape(label)}</b>\n"
                    f"Роль: <b>{ROLE_TITLES[role]}</b>\n"
                    f"Фракція: <b>{ROLE_FACTIONS[role]}</b>\n\n"
                    f"{ROLE_DESCRIPTIONS[role]}"
                ),
            )
        return

    if action == "flow":
        await query.message.answer(
            "🔥 <b>ЗНАЙОМСТВО БІЛЯ БАГАТТЯ</b>\n\n"
            "Перед першою ніччю всі представляються й знайомляться. Голосування та нічних дій ще немає.\n"
            "⏱ 180 сек. Ведучий може завершити раніше."
        )
        await query.message.answer(
            "🌘 <b>Ніч у Зоні — ходка 1</b>\n\n"
            "Табір стих. Нічні ролі отримали завдання на ПДА.\n⏱ 90 сек."
        )
        await query.message.answer(
            "🔥 <b>Сходка біля багаття</b>\n\n"
            "Після світанку живі обговорюють підозри.\n⏱ 180 сек."
        )
        await query.message.answer(
            "🗳 <b>Рішення табору</b>\n\n"
            "Кожен живий учасник отримує таємний вибір на ПДА.\n⏱ 90 сек."
        )
        await query.message.answer(
            "📟 <b>Останнє слово</b>\n\n"
            "Вигнаний голосуванням має 30 секунд на одне власне текстове повідомлення."
        )
        return

    if action == "night":
        panels = (
            ("🔪 <b>Братва: кого прибрати?</b>", "Двоє бандитів мають обрати одну ціль."),
            ("🔎 <b>Розвідник: кого перевірити?</b>", "ПДА покаже: ЗАГРОЗА або ЧИСТО."),
            ("💉 <b>Польовий медик: кого підлатати?</b>", "Можна рятувати й себе."),
            ("🧛 <b>Полювання Кровососа</b>", "Можна обрати будь-яку іншу живу ціль."),
        )
        for title, text in panels:
            await query.message.answer(f"{title}\n{text}", reply_markup=sample_targets())
        return

    if action == "event":
        event = choose_zone_event("day", chance=1.0)
        await query.message.answer(event or "☢️ Цього разу Зона мовчить.")
        return

    if action == "death":
        await query.message.answer(
            "🌅 <b>Світанок у Зоні</b>\n\n" + night_death_line("№3 «Туман»")
        )
        return

    if action == "morning":
        await query.message.answer(saved_text())
        await query.message.answer(quiet_night_text())
        return

    await query.message.answer("🧪 Невідомий тест.")
