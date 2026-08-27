from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.economy import EconomyService
from app.economy_models import EconomyAccount, ShopItem
from app.pda_renderer import render_pda_card, theme_key_from_label, theme_name
from app.zone_service import ZoneGameService

router = Router()


def _home_keyboard(*, is_admin: bool) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text="🛒 Магазин", callback_data="eco:shop"),
            InlineKeyboardButton(text="🎨 Редактор ПДА", callback_data="eco:editor"),
        ],
        [
            InlineKeyboardButton(text="🧿 Колекція", callback_data="eco:trophies"),
            InlineKeyboardButton(text="🏷 Звання", callback_data="eco:ranks"),
        ],
        [
            InlineKeyboardButton(text="📊 Статистика", callback_data="eco:stats"),
            InlineKeyboardButton(text="🧾 Історія хабару", callback_data="eco:history"),
        ],
        [InlineKeyboardButton(text="📖 Правила", callback_data="eco:rules")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton(text="🛡 Адмін-панель", callback_data="eco:admin")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _back_editor() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ До редактора", callback_data="eco:editor")]]
    )


async def _visual_home_payload(
    economy: EconomyService,
    user_id: int,
    *,
    theme_key: str | None = None,
) -> tuple[bytes, dict[str, object]]:
    data = await economy.profile_data(user_id)
    key = theme_key or theme_key_from_label(str(data["theme"]))
    return render_pda_card(data, user_id=user_id, theme_key=key), data


async def _send_visual_home(message: Message, economy: EconomyService, user_id: int) -> None:
    card, data = await _visual_home_payload(economy, user_id)
    await message.answer_photo(
        BufferedInputFile(card, filename=f"pda-{user_id}.png"),
        caption=(
            "📟 <b>ОСОБИСТИЙ ПДА</b>\n"
            f"🎨 {html.escape(str(data['theme']))}\n\n"
            "Магазин, колекція та редактор доступні навіть між ходками."
        ),
        reply_markup=_home_keyboard(is_admin=economy.is_admin(user_id)),
    )


@router.message(F.chat.type == ChatType.PRIVATE, F.text.regexp(r"^/start(?:@\w+)?$"))
async def visual_start(
    message: Message,
    game_service: ZoneGameService,
    economy_service: EconomyService,
) -> None:
    if message.from_user is None:
        return
    await game_service.ensure_user(message.from_user)
    await economy_service.ensure_account(message.from_user.id)
    await _send_visual_home(message, economy_service, message.from_user.id)


@router.message(Command("pda"), F.chat.type == ChatType.PRIVATE)
async def visual_pda(message: Message, game_service: ZoneGameService, economy_service: EconomyService) -> None:
    if message.from_user is None:
        return
    await game_service.ensure_user(message.from_user)
    await economy_service.ensure_account(message.from_user.id)
    await _send_visual_home(message, economy_service, message.from_user.id)


@router.callback_query(F.data == "eco:home")
async def visual_home_callback(query: CallbackQuery, economy_service: EconomyService) -> None:
    if query.message is None:
        return
    await query.answer()
    await _send_visual_home(query.message, economy_service, query.from_user.id)


async def _standard_activate(economy: EconomyService, user_id: int) -> None:
    await economy.ensure_account(user_id)
    async with economy.session_factory() as session:
        account = await session.get(EconomyAccount, user_id)
        if account is None:
            raise ValueError("Профіль ПДА не знайдено.")
        account.active_theme = "pda_standard"
        await session.commit()


async def _theme_item(economy: EconomyService, item_key: str) -> ShopItem | None:
    async with economy.session_factory() as session:
        return await session.get(ShopItem, item_key)


@router.callback_query(F.data.startswith("eco:item:pda_"))
async def visual_theme_preview(query: CallbackQuery, economy_service: EconomyService) -> None:
    if query.message is None or not query.data:
        return
    await query.answer()
    item_key = query.data.split(":", 2)[2]
    data = await economy_service.profile_data(query.from_user.id)
    card = render_pda_card(data, user_id=query.from_user.id, theme_key=item_key)

    if item_key == "pda_standard":
        caption = (
            "👁 <b>ПЕРЕДПЕРЕГЛЯД</b>\n"
            f"{theme_name(item_key)}\n\n"
            "Базове оформлення. Завжди доступне безкоштовно."
        )
        rows = [
            [InlineKeyboardButton(text="✅ Використовувати", callback_data="eco:activate:pda_standard")],
            [InlineKeyboardButton(text="↩️ До редактора", callback_data="eco:editor")],
        ]
    else:
        item = await _theme_item(economy_service, item_key)
        if item is None:
            await query.message.answer("⚠️ Оформлення не знайдено.", reply_markup=_back_editor())
            return
        _, owned, balance = await economy_service.shop_for_user(query.from_user.id, "theme")
        caption = (
            "👁 <b>ПЕРЕДПЕРЕГЛЯД ОФОРМЛЕННЯ</b>\n"
            f"{html.escape(item.name)}\n\n"
            f"{html.escape(item.description)}\n"
            f"💰 Ціна: <b>{item.price}</b>\n"
            f"📦 Схрон: <b>{balance}</b>"
        )
        rows = []
        if item.key in owned:
            rows.append([InlineKeyboardButton(text="✅ Використовувати", callback_data=f"eco:activate:{item.key}")])
        else:
            rows.append([InlineKeyboardButton(text=f"💰 Купити за {item.price}", callback_data=f"eco:buy:{item.key}")])
        rows.append([InlineKeyboardButton(text="↩️ До магазину", callback_data="eco:shopcat:theme")])

    await query.message.answer_photo(
        BufferedInputFile(card, filename=f"preview-{item_key}.png"),
        caption=caption,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(F.data.startswith("eco:buy:pda_"))
async def visual_theme_buy(query: CallbackQuery, economy_service: EconomyService) -> None:
    if query.message is None or not query.data:
        return
    await query.answer()
    item_key = query.data.split(":", 2)[2]
    try:
        item, balance = await economy_service.purchase(query.from_user.id, item_key)
    except ValueError as exc:
        await query.message.answer(f"⚠️ {html.escape(str(exc))}", reply_markup=_back_editor())
        return

    data = await economy_service.profile_data(query.from_user.id)
    card = render_pda_card(data, user_id=query.from_user.id, theme_key=item_key)
    await query.message.answer_photo(
        BufferedInputFile(card, filename=f"bought-{item_key}.png"),
        caption=(
            f"✅ <b>Куплено: {html.escape(item.name)}</b>\n"
            f"📦 Залишок у схроні: <b>{balance}</b>\n\n"
            "Оформлення вже у твоєму інвентарі."
        ),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ Використовувати зараз", callback_data=f"eco:activate:{item_key}")],
                [InlineKeyboardButton(text="↩️ До редактора", callback_data="eco:editor")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("eco:activate:pda_"))
async def visual_theme_activate(query: CallbackQuery, economy_service: EconomyService) -> None:
    if query.message is None or not query.data:
        return
    await query.answer()
    item_key = query.data.split(":", 2)[2]
    try:
        if item_key == "pda_standard":
            await _standard_activate(economy_service, query.from_user.id)
            activated_name = theme_name(item_key)
        else:
            activated_name = await economy_service.activate(query.from_user.id, item_key)
    except ValueError as exc:
        await query.message.answer(f"⚠️ {html.escape(str(exc))}", reply_markup=_back_editor())
        return

    card, data = await _visual_home_payload(economy_service, query.from_user.id, theme_key=item_key)
    await query.message.answer_photo(
        BufferedInputFile(card, filename=f"active-{item_key}.png"),
        caption=f"✅ Активовано: <b>{html.escape(str(activated_name))}</b>",
        reply_markup=_home_keyboard(is_admin=economy_service.is_admin(query.from_user.id)),
    )


@router.callback_query(F.data == "eco:editor")
async def visual_editor(query: CallbackQuery, economy_service: EconomyService) -> None:
    if query.message is None:
        return
    await query.answer()
    themes = await economy_service.inventory(query.from_user.id, "theme")
    titles = await economy_service.inventory(query.from_user.id, "title")
    data = await economy_service.profile_data(query.from_user.id)

    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="👁 📟 Стандартний ПДА", callback_data="eco:item:pda_standard")]
    ]
    rows.extend(
        [InlineKeyboardButton(text=f"👁 {item.name}", callback_data=f"eco:item:{item.key}")]
        for item in themes
    )
    if titles:
        rows.append([InlineKeyboardButton(text="── ТИТУЛИ ──", callback_data="eco:noop")])
        rows.extend(
            [InlineKeyboardButton(text=f"🏷 {item.name}", callback_data=f"eco:activate:{item.key}")]
            for item in titles
        )
    rows.extend(
        [
            [InlineKeyboardButton(text="🛒 Інші оформлення", callback_data="eco:shopcat:theme")],
            [InlineKeyboardButton(text="↩️ До ПДА", callback_data="eco:home")],
        ]
    )

    await query.message.answer(
        "🎨 <b>РЕДАКТОР ПДА</b>\n\n"
        f"Активне оформлення: <b>{html.escape(str(data['theme']))}</b>\n\n"
        "Натисни 👁, щоб побачити справжній вигляд теми з твоїми даними. "
        "Після покупки тема назавжди залишається у твоєму інвентарі.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )
