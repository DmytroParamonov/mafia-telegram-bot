from __future__ import annotations

import html

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.economy import RANKS, EconomyService
from app.economy_models import ShopItem, TrophyCatalog
from app.help_content import HELP_HOME
from app.keyboards import help_keyboard
from app.service import GameError
from app.zone_service import ZoneGameService

router = Router()


def pda_home_keyboard(*, is_admin: bool = False) -> InlineKeyboardMarkup:
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


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="↩️ До ПДА", callback_data="eco:home")]]
    )


def shop_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎨 Оформлення ПДА", callback_data="eco:shopcat:theme"),
                InlineKeyboardButton(text="🏷 Титули", callback_data="eco:shopcat:title"),
            ],
            [InlineKeyboardButton(text="🧿 Вітрина трофеїв", callback_data="eco:shopcat:slot")],
            [InlineKeyboardButton(text="↩️ До ПДА", callback_data="eco:home")],
        ]
    )


def _theme_header(theme: str) -> tuple[str, str]:
    if "Військовий" in theme:
        return "🪖 <b>ВІЙСЬКОВИЙ ПДА // ONLINE</b>", "━━━━━━━━━━━━━━━━"
    if "Темний" in theme:
        return "🌑 <b>BLACK-LINK PDA</b>", "················"
    if "Аварійний" in theme:
        return "🔴 <b>⚠ АВАРІЙНИЙ КАНАЛ ПДА ⚠</b>", "════════════════"
    if "Польовий" in theme:
        return "☢️ <b>ПОЛЬОВИЙ ПДА // ZONE NET</b>", "╾──────────────╼"
    if "Чорний" in theme:
        return "⬛ <b>BLACK PDA // SECURE</b>", "▰▰▰▰▰▰▰▰"
    if "Легенди" in theme:
        return "⭐ <b>ПДА ЛЕГЕНДИ ЗОНИ</b> ⭐", "✦ ─────────── ✦"
    return "📟 <b>ТВІЙ ПДА</b>", "──────────────"


async def render_home(economy: EconomyService, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    data = await economy.profile_data(user_id)
    header, divider = _theme_header(str(data["theme"]))
    title = f"\n🎖 {html.escape(str(data['title']))}" if data["title"] else ""
    next_rank = data["next_rank"]
    if next_rank:
        rank_line = f"\nДо «{html.escape(next_rank[0])}»: <b>{next_rank[1]} хабару</b>"
    else:
        rank_line = "\n🏆 Максимальне звання досягнуто."
    showcase = data["showcase"]
    if showcase:
        showcase_text = "\n".join(f"  {slot}. {html.escape(name)}" for slot, name in showcase)
    else:
        showcase_text = "  <i>Вітрина порожня</i>"

    text = (
        f"{header}\n{divider}\n\n"
        f"👤 <b>{html.escape(str(data['name']))}</b>{title}\n"
        f"🏷 Звання: <b>{html.escape(str(data['rank']))}</b>\n"
        f"📦 Схрон: <b>{data['balance']} хабару</b>\n"
        f"📈 Зароблено за весь час: <b>{data['lifetime_earned']}</b>"
        f"{rank_line}\n\n"
        f"🎨 Оформлення: <b>{html.escape(str(data['theme']))}</b>\n"
        f"🧿 Колекція: <b>{data['trophy_count']}</b> різних трофеїв\n"
        f"🖼 <b>Вітрина:</b>\n{showcase_text}\n\n"
        "<i>Хабар дає тільки косметику, колекцію та статус. Переваг у самій Мафії він не купує.</i>"
    )
    return text, pda_home_keyboard(is_admin=economy.is_admin(user_id))


async def send_home(message: Message, economy: EconomyService) -> None:
    if message.from_user is None:
        return
    text, markup = await render_home(economy, message.from_user.id)
    await message.answer(text, reply_markup=markup)


# Exact plain /start only. Deep links such as /start join_123 continue to the
# existing game router because this filter does not match text with arguments.
@router.message(F.chat.type == ChatType.PRIVATE, F.text.regexp(r"^/start(?:@\w+)?$"))
async def economy_start(message: Message, game_service: ZoneGameService, economy_service: EconomyService) -> None:
    if message.from_user is None:
        return
    await game_service.ensure_user(message.from_user)
    await economy_service.ensure_account(message.from_user.id)
    await send_home(message, economy_service)


@router.message(Command("pda"))
async def pda_command(message: Message, game_service: ZoneGameService, economy_service: EconomyService) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("📟 ПДА відкривається в особистому чаті з ботом.")
        return
    if message.from_user is None:
        return
    await game_service.ensure_user(message.from_user)
    await economy_service.ensure_account(message.from_user.id)
    await send_home(message, economy_service)


@router.message(Command("shop"))
async def shop_command(message: Message, game_service: ZoneGameService, economy_service: EconomyService) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("🛒 Магазин працює в особистому ПДА.")
        return
    if message.from_user is None:
        return
    await game_service.ensure_user(message.from_user)
    await economy_service.ensure_account(message.from_user.id)
    data = await economy_service.profile_data(message.from_user.id)
    await message.answer(
        "🛒 <b>ТОРГОВЕЦЬ</b>\n\n"
        f"📦 У схроні: <b>{data['balance']} хабару</b>\n\n"
        "Тут продається тільки косметика та місця для трофеїв. Ігрових переваг немає.",
        reply_markup=shop_keyboard(),
    )


@router.message(Command("id"))
async def id_command(message: Message) -> None:
    if message.from_user is None:
        return
    await message.answer(
        "🪪 <b>Твій Telegram ID</b>\n\n"
        f"<code>{message.from_user.id}</code>\n\n"
        "Він потрібен власнику бота для доступу до адмін-панелі економіки."
    )


def _admin_recent_keyboard(users) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"👤 {user.display_name[:28]}",
                callback_data=f"eco:adminuser:{user.id}",
            )
        ]
        for user in users
    ]
    rows.append([InlineKeyboardButton(text="↩️ До ПДА", callback_data="eco:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("admin"))
async def admin_command(message: Message, economy_service: EconomyService) -> None:
    if message.from_user is None or not economy_service.is_admin(message.from_user.id):
        await message.answer(
            "🛡 Адмін-панель недоступна.\n\n"
            "Якщо це твій бот: напиши /id, додай свій ID у <code>ADMIN_USER_IDS</code> в .env і перезапусти бота."
        )
        return
    users = await economy_service.recent_users()
    await message.answer(
        "🛡 <b>АДМІН-ПАНЕЛЬ ЕКОНОМІКИ</b>\n\n"
        "Останні гравці в базі. Усі ручні зміни хабару записуються в журнал транзакцій.",
        reply_markup=_admin_recent_keyboard(users),
    )


@router.message(Command("habar"))
async def habar_admin_command(
    message: Message,
    command: CommandObject,
    game_service: ZoneGameService,
    economy_service: EconomyService,
) -> None:
    if message.from_user is None or not economy_service.is_admin(message.from_user.id):
        await message.answer("⛔ Команда доступна лише адміністратору економіки.")
        return

    args = (command.args or "").split()
    target_user_id: int | None = None
    amount_token: str | None = None
    reason_parts: list[str] = []

    replied = message.reply_to_message.from_user if message.reply_to_message else None
    if replied is not None:
        await game_service.ensure_user(replied)
        target_user_id = replied.id
        if args:
            amount_token = args[0]
            reason_parts = args[1:]
    elif len(args) >= 2:
        target = await economy_service.find_user(args[0])
        if target is not None:
            target_user_id = target.id
        amount_token = args[1]
        reason_parts = args[2:]

    if target_user_id is None or amount_token is None:
        await message.answer(
            "💰 <b>Як користуватися</b>\n\n"
            "Відповідай на повідомлення гравця:\n<code>/habar +500 Турнір</code>\n\n"
            "або:\n<code>/habar @username +500 Турнір</code>\n"
            "<code>/habar 123456789 -100 Корекція</code>"
        )
        return

    try:
        amount = int(amount_token)
        if abs(amount) > 1_000_000:
            raise ValueError
    except ValueError:
        await message.answer("⚠️ Некоректна сума.")
        return

    reason = " ".join(reason_parts).strip() or f"Адмін: {message.from_user.full_name}"
    try:
        balance = await economy_service.adjust_balance(target_user_id, amount, reason)
    except ValueError as exc:
        await message.answer(f"⚠️ {html.escape(str(exc))}")
        return
    sign = "+" if amount > 0 else ""
    await message.answer(
        f"✅ Зміна записана: <b>{sign}{amount} хабару</b>.\n"
        f"👤 ID: <code>{target_user_id}</code>\n"
        f"📦 Новий баланс: <b>{balance}</b>\n"
        f"🧾 Причина: {html.escape(reason)}"
    )


@router.callback_query(F.data.startswith("eco:"))
async def economy_callback(
    query: CallbackQuery,
    economy_service: EconomyService,
    game_service: ZoneGameService,
) -> None:
    if query.from_user is None or query.message is None or not query.data:
        return
    parts = query.data.split(":")
    action = parts[1] if len(parts) > 1 else ""
    user_id = query.from_user.id
    await query.answer()

    if action == "home":
        text, markup = await render_home(economy_service, user_id)
        await query.message.answer(text, reply_markup=markup)
        return

    if action == "shop":
        data = await economy_service.profile_data(user_id)
        await query.message.answer(
            "🛒 <b>ТОРГОВЕЦЬ</b>\n\n"
            f"📦 У схроні: <b>{data['balance']} хабару</b>\n"
            "Обери розділ:",
            reply_markup=shop_keyboard(),
        )
        return

    if action == "shopcat" and len(parts) == 3:
        category = parts[2]
        items, owned, balance = await economy_service.shop_for_user(user_id, category)
        labels = {"theme": "🎨 Оформлення ПДА", "title": "🏷 Титули", "slot": "🧿 Вітрина"}
        rows = []
        for item in items:
            mark = "✅" if item.key in owned else f"💰{item.price}"
            rows.append(
                [InlineKeyboardButton(text=f"{item.name} — {mark}", callback_data=f"eco:item:{item.key}")]
            )
        rows.append([InlineKeyboardButton(text="↩️ До магазину", callback_data="eco:shop")])
        await query.message.answer(
            f"{labels.get(category, '🛒 Магазин')}\n\n📦 Баланс: <b>{balance}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return

    if action == "item" and len(parts) == 3:
        item_key = parts[2]
        async with economy_service.session_factory() as session:
            item = await session.get(ShopItem, item_key)
        if item is None:
            await query.message.answer("⚠️ Товар не знайдено.", reply_markup=back_home())
            return
        _, owned, balance = await economy_service.shop_for_user(user_id, item.category)
        rows = []
        if item.key in owned:
            if item.category in {"theme", "title"}:
                rows.append([InlineKeyboardButton(text="🎨 Використовувати", callback_data=f"eco:activate:{item.key}")])
            else:
                rows.append([InlineKeyboardButton(text="✅ Уже придбано", callback_data="eco:noop")])
        else:
            rows.append([InlineKeyboardButton(text=f"💰 Купити за {item.price}", callback_data=f"eco:buy:{item.key}")])
        rows.append([InlineKeyboardButton(text="↩️ До магазину", callback_data="eco:shop")])
        await query.message.answer(
            f"<b>{item.name}</b>\n\n{html.escape(item.description)}\n\n"
            f"💰 Ціна: <b>{item.price}</b>\n📦 Баланс: <b>{balance}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return

    if action == "buy" and len(parts) == 3:
        try:
            item, balance = await economy_service.purchase(user_id, parts[2])
        except ValueError as exc:
            await query.message.answer(f"⚠️ {html.escape(str(exc))}", reply_markup=back_home())
            return
        rows = []
        if item.category in {"theme", "title"}:
            rows.append([InlineKeyboardButton(text="🎨 Використовувати зараз", callback_data=f"eco:activate:{item.key}")])
        rows.append([InlineKeyboardButton(text="↩️ До магазину", callback_data="eco:shop")])
        await query.message.answer(
            f"✅ <b>Куплено: {item.name}</b>\n\n📦 Залишок у схроні: <b>{balance}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return

    if action == "activate" and len(parts) == 3:
        try:
            name = await economy_service.activate(user_id, parts[2])
        except ValueError as exc:
            await query.message.answer(f"⚠️ {html.escape(str(exc))}", reply_markup=back_home())
            return
        await query.message.answer(f"✅ Активовано: <b>{name}</b>", reply_markup=back_home())
        return

    if action == "editor":
        themes = await economy_service.inventory(user_id, "theme")
        titles = await economy_service.inventory(user_id, "title")
        rows = [
            [InlineKeyboardButton(text=item.name, callback_data=f"eco:activate:{item.key}")]
            for item in themes
        ]
        rows += [
            [InlineKeyboardButton(text=f"🏷 {item.name}", callback_data=f"eco:activate:{item.key}")]
            for item in titles
        ]
        rows.append([InlineKeyboardButton(text="↩️ До ПДА", callback_data="eco:home")])
        text = "🎨 <b>РЕДАКТОР ПДА</b>\n\n"
        if themes or titles:
            text += "Натисни на придбане оформлення або титул, щоб активувати."
        else:
            text += "Поки нічого не придбано. Зазирни до магазину."
        await query.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
        return

    if action == "trophies":
        trophies = await economy_service.trophies(user_id)
        data = await economy_service.profile_data(user_id)
        rows = [
            [InlineKeyboardButton(text=f"{catalog.name} ×{owned.quantity}", callback_data=f"eco:trophy:{catalog.key}")]
            for owned, catalog in trophies
        ]
        rows.append([InlineKeyboardButton(text="↩️ До ПДА", callback_data="eco:home")])
        await query.message.answer(
            "🧿 <b>КОЛЕКЦІЯ ТРОФЕЇВ</b>\n\n"
            f"Знайдено різних: <b>{len(trophies)}</b>\n"
            f"Відкрито слотів вітрини: <b>{data['showcase_slots']}</b>\n\n"
            + ("Обери трофей, щоб прочитати опис або поставити його на вітрину." if trophies else "Перший трофей може випасти після завершеної ходки."),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return

    if action == "trophy" and len(parts) == 3:
        trophy_key = parts[2]
        data = await economy_service.profile_data(user_id)
        async with economy_service.session_factory() as session:
            trophy = await session.get(TrophyCatalog, trophy_key)
        if trophy is None:
            return
        rows = [
            [InlineKeyboardButton(text=f"🖼 Поставити в слот {slot}", callback_data=f"eco:showcase:{slot}:{trophy_key}")]
            for slot in range(1, int(data["showcase_slots"]) + 1)
        ]
        rows.append([InlineKeyboardButton(text="↩️ До колекції", callback_data="eco:trophies")])
        await query.message.answer(
            f"<b>{trophy.name}</b>\n\n{html.escape(trophy.description)}\n\n"
            f"Рідкість: <b>{html.escape(trophy.rarity.upper())}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return

    if action == "showcase" and len(parts) == 4:
        try:
            await economy_service.set_showcase(user_id, int(parts[2]), parts[3])
        except (ValueError, TypeError) as exc:
            await query.message.answer(f"⚠️ {html.escape(str(exc))}", reply_markup=back_home())
            return
        await query.message.answer("✅ Трофей виставлено у ПДА.", reply_markup=back_home())
        return

    if action == "ranks":
        data = await economy_service.profile_data(user_id)
        lines = ["🏷 <b>ЗВАННЯ ЗОНИ</b>", "", f"Твоє звання: <b>{data['rank']}</b>", f"Зароблено всього: <b>{data['lifetime_earned']}</b>", ""]
        for threshold, name in RANKS:
            mark = "✅" if int(data["lifetime_earned"]) >= threshold else "🔒"
            lines.append(f"{mark} <b>{name}</b> — {threshold}")
        lines.append("\n<i>Покупки не знижують звання: воно рахується за весь хабар, який ти коли-небудь заробив.</i>")
        await query.message.answer("\n".join(lines), reply_markup=back_home())
        return

    if action == "stats":
        await query.message.answer(await game_service.stats_text(user_id), reply_markup=back_home())
        return

    if action == "history":
        history = await economy_service.transaction_history(user_id)
        lines = ["🧾 <b>ОСТАННІ ОПЕРАЦІЇ</b>", ""]
        if not history:
            lines.append("Поки порожньо.")
        for row in history:
            sign = "+" if row.amount > 0 else ""
            note = f" — {html.escape(row.note)}" if row.note else ""
            lines.append(f"• <b>{sign}{row.amount}</b> | {html.escape(row.kind)}{note}")
        await query.message.answer("\n".join(lines), reply_markup=back_home())
        return

    if action == "rules":
        await query.message.answer(HELP_HOME, reply_markup=help_keyboard())
        return

    if action == "admin":
        if not economy_service.is_admin(user_id):
            await query.answer("Немає доступу.", show_alert=True)
            return
        users = await economy_service.recent_users()
        await query.message.answer(
            "🛡 <b>АДМІН-ПАНЕЛЬ</b>\n\nОбери гравця:",
            reply_markup=_admin_recent_keyboard(users),
        )
        return

    if action == "adminuser" and len(parts) == 3:
        if not economy_service.is_admin(user_id):
            return
        target_id = int(parts[2])
        data = await economy_service.profile_data(target_id)
        rows = [
            [
                InlineKeyboardButton(text="+100", callback_data=f"eco:grant:{target_id}:100"),
                InlineKeyboardButton(text="+500", callback_data=f"eco:grant:{target_id}:500"),
                InlineKeyboardButton(text="+1000", callback_data=f"eco:grant:{target_id}:1000"),
            ],
            [InlineKeyboardButton(text="−100", callback_data=f"eco:grant:{target_id}:-100")],
            [InlineKeyboardButton(text="↩️ До адмінки", callback_data="eco:admin")],
        ]
        await query.message.answer(
            f"👤 <b>{html.escape(str(data['name']))}</b>\n"
            f"ID: <code>{target_id}</code>\n"
            f"📦 Схрон: <b>{data['balance']}</b>\n"
            f"🏷 {data['rank']}\n\n"
            "Для довільної суми використовуй /habar.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        )
        return

    if action == "grant" and len(parts) == 4:
        if not economy_service.is_admin(user_id):
            return
        target_id = int(parts[2])
        amount = int(parts[3])
        try:
            balance = await economy_service.adjust_balance(
                target_id,
                amount,
                f"Швидке адмін-нарахування від {query.from_user.full_name}",
            )
        except ValueError as exc:
            await query.message.answer(f"⚠️ {html.escape(str(exc))}")
            return
        sign = "+" if amount > 0 else ""
        await query.message.answer(
            f"✅ <b>{sign}{amount}</b> хабару. Новий баланс ID {target_id}: <b>{balance}</b>",
            reply_markup=back_home(),
        )
        return

    if action == "noop":
        return

    raise GameError("Невідома кнопка економіки.")
