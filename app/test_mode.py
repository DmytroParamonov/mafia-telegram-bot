from __future__ import annotations

import html
import random

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.game.rules import (
    ROLE_DESCRIPTIONS,
    ROLE_FACTIONS,
    ROLE_TITLES,
    Role,
    build_zone_roles,
    zone_role_counts,
)
from app.live_zone import live_zone_effect, phase_seconds
from app.private_role_art import PRIVATE_ART_ROOT, ROLE_ART, load_private_role_art, private_role_art_path
from app.zone_features import (
    CALLSIGNS,
    INTRO_SECONDS,
    choose_zone_event,
    night_death_line,
    quiet_night_text,
    saved_text,
)

router = Router()

TEST_ROLES = (
    Role.CIVILIAN.value,
    Role.MAFIA.value,
    Role.SHERIFF.value,
    Role.DOCTOR.value,
    Role.BLOODSUCKER.value,
)

ROLE_SHORT = {
    Role.CIVILIAN.value: "☢️ Сталкер",
    Role.MAFIA.value: "🔪 Бандит",
    Role.SHERIFF.value: "🔎 Розвідник",
    Role.DOCTOR.value: "💉 Медик",
    Role.BLOODSUCKER.value: "🧛 Кровосос",
}


def test_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎴 Картки ПДА", callback_data="t:cards"),
                InlineKeyboardButton(text="📦 Перевірити 18 артів", callback_data="t:cardpack"),
            ],
            [
                InlineKeyboardButton(text="🔥 Етапи ходки", callback_data="t:flow"),
                InlineKeyboardButton(text="🌘 Нічні ПДА", callback_data="t:night"),
            ],
            [
                InlineKeyboardButton(text="🎒 Готовність", callback_data="t:ready"),
                InlineKeyboardButton(text="⚖️ Баланс 5–10", callback_data="t:balance"),
            ],
            [InlineKeyboardButton(text="🎲 Симуляція партії", callback_data="t:sim_menu")],
            [
                InlineKeyboardButton(text="☢️ Жива Зона", callback_data="t:livezone"),
                InlineKeyboardButton(text="🌫 Атмосферна подія", callback_data="t:event"),
            ],
            [
                InlineKeyboardButton(text="☠️ Смерть", callback_data="t:death"),
                InlineKeyboardButton(text="💉 Порятунок / тиха ніч", callback_data="t:morning"),
            ],
        ]
    )


def card_role_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=ROLE_SHORT[role], callback_data=f"t:card:{role}:0")]
            for role in TEST_ROLES
        ]
        + [[InlineKeyboardButton(text="↩️ До тестів", callback_data="t:menu")]]
    )


def card_nav(role: str, index: int) -> InlineKeyboardMarkup:
    count = len(ROLE_ART.get(role, ()))
    if count <= 1:
        navigation = [
            InlineKeyboardButton(text=f"{1 if count else 0}/{count}", callback_data="t:noop")
        ]
    else:
        previous = (index - 1) % count
        following = (index + 1) % count
        navigation = [
            InlineKeyboardButton(text="◀️", callback_data=f"t:card:{role}:{previous}"),
            InlineKeyboardButton(text=f"{index + 1}/{count}", callback_data="t:noop"),
            InlineKeyboardButton(text="▶️", callback_data=f"t:card:{role}:{following}"),
        ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            navigation,
            [InlineKeyboardButton(text="🎴 Інша роль", callback_data="t:cards")],
            [InlineKeyboardButton(text="↩️ До тестів", callback_data="t:menu")],
        ]
    )


def simulation_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=str(count), callback_data=f"t:sim:{count}")
                for count in range(start, min(start + 3, 11))
            ]
            for start in (5, 8)
        ]
        + [[InlineKeyboardButton(text="↩️ До тестів", callback_data="t:menu")]]
    )


def sample_targets() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="№2 «Саня Кабан» — Олександр", callback_data="t:noop")],
            [InlineKeyboardButton(text="№3 «Серьога Ворон» — Вадим", callback_data="t:noop")],
            [InlineKeyboardButton(text="№4 «Коля Тихий» — Лена", callback_data="t:noop")],
        ]
    )


async def _send_local_card(message: Message, role: str, index: int) -> None:
    pool = ROLE_ART.get(role, ())
    if not pool:
        await message.answer("🧪 Невідома роль для тесту.")
        return

    index %= len(pool)
    art = pool[index]
    path = private_role_art_path(art)
    if path is None:
        expected = PRIVATE_ART_ROOT / role / f"{art.asset_key}.jpg"
        await message.answer(
            "⚠️ <b>Локальний арт не знайдено.</b>\n\n"
            f"Персонаж: <b>{html.escape(art.internal_name)}</b>\n"
            f"Поклади файл сюди:\n<code>{html.escape(str(expected))}</code>\n\n"
            "Також підійдуть .jpeg, .png або .webp з тим самим номером.",
            reply_markup=card_nav(role, index),
        )
        return

    image = load_private_role_art(art)
    await message.answer_photo(
        BufferedInputFile(image, filename=path.name),
        caption=(
            f"📟 <b>Локальний арт #{index + 1}</b>\n\n"
            f"Персонаж: <b>{html.escape(art.internal_name)}</b>\n"
            f"Роль: <b>{ROLE_TITLES[role]}</b>\n"
            f"Фракція: <b>{ROLE_FACTIONS[role]}</b>\n\n"
            f"{ROLE_DESCRIPTIONS[role]}"
        ),
        reply_markup=card_nav(role, index),
    )


@router.message(Command("test"))
async def test_command(message: Message) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer(
            "🧪 <b>Тестовий полігон працює в особистому ПДА.</b>\n\n"
            "Відкрий особистий чат із ботом і напиши /test. Тут не потрібні 5 гравців "
            "і не створюється справжня ходка."
        )
        return

    await message.answer(
        "🧪 <b>ТЕСТОВИЙ ПОЛІГОН ПДА</b>\n\n"
        "Тут можна одному перевіряти локальні арти ПДА, етапи, нічні меню, баланс, події, "
        "режим «Жива Зона» і симуляцію складу. Тест не записується в статистику й не "
        "запускає справжню партію.",
        reply_markup=test_menu(),
    )


@router.callback_query(F.data.startswith("t:"))
async def test_callback(query: CallbackQuery) -> None:
    if query.from_user is None or not query.data:
        return
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "noop":
        await query.answer("🧪 Це лише тестовий індикатор.")
        return

    if query.message is None:
        await query.answer()
        return

    await query.answer()

    if action == "menu":
        await query.message.answer("🧪 <b>Тестовий полігон</b>", reply_markup=test_menu())
        return

    if action == "cards":
        await query.message.answer(
            "🎴 <b>Локальні арти ПДА</b>\n\n"
            "Обери роль. Тут показуються тільки твої файли з <code>data/private_role_art/</code>: "
            "5 Бандитів, 10 Вільних, Медик, Розвідник і Кровосос.",
            reply_markup=card_role_menu(),
        )
        return

    if action == "card" and len(parts) == 4:
        try:
            index = int(parts[3])
        except ValueError:
            await query.message.answer("🧪 Некоректний номер картки.")
            return
        await _send_local_card(query.message, parts[2], index)
        return

    if action == "cardpack":
        present = 0
        missing: list[str] = []
        for role, pool in ROLE_ART.items():
            for art in pool:
                if private_role_art_path(art) is not None:
                    present += 1
                else:
                    missing.append(f"• {role}/{art.asset_key}.jpg — {art.internal_name}")

        total = sum(len(pool) for pool in ROLE_ART.values())
        text = (
            "📦 <b>Перевірка локальних артів</b>\n\n"
            f"Знайдено: <b>{present}/{total}</b>.\n"
            f"Папка: <code>{PRIVATE_ART_ROOT}</code>"
        )
        if missing:
            text += "\n\n⚠️ <b>Не знайдено:</b>\n" + "\n".join(missing)
        else:
            text += "\n\n✅ Усі 18 приватних артів на місці. Бот братиме саме їх у реальній ходці."
        await query.message.answer(text)
        return

    if action == "flow":
        await query.message.answer(
            "🔥 <b>ЗНАЙОМСТВО БІЛЯ БАГАТТЯ</b>\n\n"
            "Перед першою ніччю всі представляються й знайомляться. Голосування та нічних дій ще немає.\n"
            f"⏱ {INTRO_SECONDS} сек. Ведучий може завершити раніше."
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

    if action == "ready":
        await query.message.answer(
            "🎒 <b>ПЕРЕВІРКА СПОРЯДЖЕННЯ</b>\n\n"
            "✅ 1. Дмитро\n"
            "✅ 2. Олександр\n"
            "⏳ 3. Вадим\n"
            "⏳ 4. Лена\n"
            "✅ 5. Андрій\n\n"
            "⏱ На підтвердження: <b>60 сек.</b>"
        )
        return

    if action == "balance":
        lines = ["⚖️ <b>Баланс 5–10 гравців</b>", ""]
        for count in range(5, 11):
            roles = zone_role_counts(count)
            lines.append(
                f"<b>{count}</b>: 🔪{roles[Role.MAFIA.value]} "
                f"🔎{roles[Role.SHERIFF.value]} "
                f"💉{roles[Role.DOCTOR.value]} "
                f"🧛{roles[Role.BLOODSUCKER.value]} "
                f"☢️{roles[Role.CIVILIAN.value]}"
            )
        await query.message.answer("\n".join(lines))
        return

    if action == "sim_menu":
        await query.message.answer(
            "🎲 <b>Симуляція складу</b>\n\nСкільки уявних гравців розкласти по ролях?",
            reply_markup=simulation_menu(),
        )
        return

    if action == "sim" and len(parts) == 3:
        try:
            count = int(parts[2])
        except ValueError:
            count = 0
        if count not in range(5, 11):
            await query.message.answer("🧪 Для симуляції доступно 5–10 гравців.")
            return
        rng = random.Random()
        roles = build_zone_roles(count, rng=rng)
        names = rng.sample(list(CALLSIGNS), count)
        roster = "\n".join(
            f"№{index} «{html.escape(callsign)}» — {ROLE_TITLES[role]}"
            for index, (callsign, role) in enumerate(zip(names, roles, strict=True), start=1)
        )
        await query.message.answer(
            f"🎲 <b>Тестова симуляція на {count}</b>\n\n{roster}\n\n"
            "Це лише локальний перегляд: статистика та база гри не змінюються."
        )
        return

    if action == "livezone":
        await query.message.answer(
            "☢️ <b>ЖИВА ЗОНА — окремий режим</b>\n\n"
            "У класичній ходці події лише створюють атмосферу. У «Живій Зоні» частина "
            "подій реально змінює тривалість поточного етапу. Ось примусова демонстрація:"
        )
        bases = {"night": 90, "discussion": 180, "voting": 90}
        labels = {"night": "🌘 Ніч", "discussion": "🔥 Сходка", "voting": "🗳 Голосування"}
        for phase, base in bases.items():
            effect = live_zone_effect(777, 1, phase, chance=1.0)
            if effect is None:
                continue
            actual = phase_seconds(base, effect)
            await query.message.answer(
                f"{labels[phase]}\n{effect.title}\n\n{effect.text}\n"
                f"⏱ Було: <b>{base}</b> → стало: <b>{actual} сек.</b>"
            )
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
