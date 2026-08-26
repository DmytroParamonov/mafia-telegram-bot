from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select

from app.help_content import HELP_HOME, help_section_text, role_help_text
from app.keyboards import confirm_end_keyboard, help_back_keyboard, help_keyboard
from app.models import GamePlayer
from app.service import GameError
from app.zone_service import ZoneGameService

router = Router()


async def _reply_error(message: Message | None, text: str) -> None:
    if message is not None:
        await message.answer(f"⚠️ {text}")


async def _send_help_home(message: Message) -> None:
    await message.answer(HELP_HOME, reply_markup=help_keyboard())


@router.message(CommandStart())
async def start_command(
    message: Message,
    command: CommandObject,
    game_service: ZoneGameService,
) -> None:
    if message.from_user is None:
        return
    await game_service.ensure_user(message.from_user)

    payload = command.args or ""
    if payload == "rules":
        await _send_help_home(message)
        return

    if payload.startswith("join_"):
        try:
            game_id = int(payload.removeprefix("join_"))
            joined = await game_service.join_game(game_id, message.from_user)
        except (ValueError, GameError) as exc:
            await message.answer(f"⚠️ Не вдалося приєднатися до ходки: {exc}")
            return

        if joined:
            await message.answer(
                "✅ <b>Ти біля багаття!</b>\n\n"
                "Коли старший завершить набір, сюди прийде перевірка готовності, а потім твій особистий ПДА з роллю."
            )
        else:
            await message.answer("✅ Ти вже береш участь у цій ходці.")
        return

    await message.answer(
        "☢️ <b>STALKER MAFIA</b>\n\n"
        "Це твій особистий ПДА. Тут приходять роль, нічні дії, таємне голосування й службові повідомлення.\n\n"
        "Щоб зібрати ходку, адміністратор групи пише /stalker.\n"
        "Правила та опис ролей завжди доступні через /help.",
        reply_markup=help_keyboard(),
    )


@router.message(Command("stalker", "mafia"))
async def stalker_command(message: Message, game_service: ZoneGameService) -> None:
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer("☢️ Нову ходку треба збирати в груповому чаті командою /stalker.")
        return
    if message.from_user is None:
        await message.answer("⚠️ Не можу визначити старшого групи. Вимкни анонімний режим адміністратора.")
        return

    existing = await game_service.get_open_game_for_chat(message.chat.id)
    if existing is not None:
        if existing.status == "lobby":
            await message.answer(
                "🔥 <b>Збір уже триває.</b>\n\nНе запускай нову ходку — просто сідай до багаття.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🔥 Сісти до багаття",
                                url=game_service.join_url(game_service.bot_username, existing.id),
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="📖 Правила",
                                url=f"https://t.me/{game_service.bot_username}?start=rules",
                            )
                        ],
                    ]
                ),
            )
        else:
            await message.answer("⚠️ У цьому чаті вже триває активна ходка.")
        return

    member = await game_service.bot.get_chat_member(message.chat.id, message.from_user.id)
    if member.status not in {ChatMemberStatus.CREATOR, ChatMemberStatus.ADMINISTRATOR}:
        await message.answer("⚠️ Нову ходку можуть збирати лише адміністратори групи.")
        return

    try:
        await game_service.create_lobby(message.chat.id, message.chat.title, message.from_user)
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


@router.message(Command("check"))
async def check_command(message: Message, game_service: ZoneGameService) -> None:
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer("Команду /check треба запускати в ігровій групі.")
        return
    await message.answer(await game_service.permission_report(message.chat.id))


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await _send_help_home(message)


@router.callback_query(F.data.startswith("help:"))
async def help_callback(query: CallbackQuery) -> None:
    if not query.data or query.message is None:
        await query.answer()
        return

    section = query.data.split(":", 1)[1]
    await query.answer()
    if section == "menu":
        await query.message.answer(HELP_HOME, reply_markup=help_keyboard())
        return

    text = help_section_text(section)
    if text is None:
        await query.message.answer("📟 Цей розділ довідника не знайдено.")
        return
    await query.message.answer(text, reply_markup=help_back_keyboard())


@router.callback_query(F.data.startswith("pda:role:"))
async def my_role_help_callback(query: CallbackQuery, game_service: ZoneGameService) -> None:
    if query.from_user is None or not query.data or query.message is None:
        return
    try:
        game_id = int(query.data.rsplit(":", 1)[1])
    except ValueError:
        await query.answer("Некоректний ПДА.", show_alert=True)
        return

    async with game_service.session_factory() as session:
        player = await session.scalar(
            select(GamePlayer).where(
                GamePlayer.game_id == game_id,
                GamePlayer.user_id == query.from_user.id,
            )
        )

    if player is None:
        await query.answer("Тебе немає в цій ходці.", show_alert=True)
        return
    text = role_help_text(player.role)
    if text is None:
        await query.answer("Роль ще не призначена.", show_alert=True)
        return

    await query.answer()
    await query.message.answer(text, reply_markup=help_back_keyboard())


@router.message(Command("stats"))
async def stats_command(message: Message, game_service: ZoneGameService) -> None:
    if message.from_user is None:
        return
    await message.answer(await game_service.stats_text(message.from_user.id))


@router.callback_query(F.data.startswith("l:"))
async def lobby_callback(query: CallbackQuery, game_service: ZoneGameService) -> None:
    if query.from_user is None or not query.data:
        return
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer("Некоректна кнопка.", show_alert=True)
        return
    _, action, raw_game_id = parts
    try:
        game_id = int(raw_game_id)
    except ValueError:
        await query.answer("Некоректна ходка.", show_alert=True)
        return

    if action == "start":
        await query.answer("🎒 Починаю перевірку спорядження…")
        try:
            await game_service.start_game(game_id, query.from_user.id)
        except GameError as exc:
            await _reply_error(query.message, str(exc))
        return

    try:
        if action == "leave":
            await game_service.leave_game(game_id, query.from_user.id)
            await query.answer("Ти відійшов від багаття.")
        elif action.startswith("toggle_"):
            await game_service.toggle_setting(game_id, query.from_user.id, action)
            await query.answer("Налаштування змінено.")
        elif action == "cancel":
            await game_service.cancel_lobby(game_id, query.from_user.id)
            await query.answer("Групу розпущено.")
        else:
            await query.answer("Невідома кнопка.", show_alert=True)
    except GameError as exc:
        await query.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("a:"))
async def night_action_callback(query: CallbackQuery, game_service: ZoneGameService) -> None:
    if query.from_user is None or not query.data:
        return
    parts = query.data.split(":")
    if len(parts) != 5:
        await query.answer("Некоректна кнопка.", show_alert=True)
        return
    _, raw_game_id, raw_day, action_code, raw_target = parts
    try:
        game_id = int(raw_game_id)
        day_number = int(raw_day)
        target_user_id = int(raw_target)
        result, complete = await game_service.submit_night_action(
            game_id=game_id,
            day_number=day_number,
            actor_user_id=query.from_user.id,
            action_code=action_code,
            target_user_id=target_user_id,
        )
    except (ValueError, GameError) as exc:
        await query.answer(str(exc), show_alert=True)
        return

    await query.answer("Вибір прийнято.")
    if query.message:
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        await query.message.answer(result)

    if complete:
        try:
            await game_service.advance_phase(game_id)
        except GameError:
            pass


@router.callback_query(F.data.startswith("v:"))
async def vote_callback(query: CallbackQuery, game_service: ZoneGameService) -> None:
    if query.from_user is None or not query.data:
        return
    parts = query.data.split(":")
    if len(parts) != 5:
        await query.answer("Некоректна кнопка.", show_alert=True)
        return
    _, raw_game_id, raw_day, raw_round, raw_target = parts
    try:
        game_id = int(raw_game_id)
        day_number = int(raw_day)
        vote_round = int(raw_round)
        target_user_id = int(raw_target)
        result, complete = await game_service.submit_vote(
            game_id=game_id,
            day_number=day_number,
            vote_round=vote_round,
            voter_user_id=query.from_user.id,
            target_user_id=target_user_id,
        )
    except (ValueError, GameError) as exc:
        await query.answer(str(exc), show_alert=True)
        return

    await query.answer("Голос прийнято.")
    if query.message:
        try:
            await query.message.edit_reply_markup(reply_markup=None)
        except TelegramBadRequest:
            pass
        await query.message.answer(result)

    if complete:
        try:
            await game_service.advance_phase(game_id)
        except GameError:
            pass


@router.callback_query(F.data.startswith("h:"))
async def host_callback(query: CallbackQuery, game_service: ZoneGameService) -> None:
    if query.from_user is None or not query.data:
        return
    parts = query.data.split(":")
    action = parts[1] if len(parts) >= 2 else ""

    if action == "dismiss" and len(parts) == 3:
        await query.answer("Скасовано.")
        if query.message:
            try:
                await query.message.delete()
            except TelegramBadRequest:
                pass
        return

    if action == "rematch" and len(parts) == 3:
        try:
            game_id = int(parts[2])
            await query.answer("🔄 Збираю ще одну ходку…")
            await game_service.rematch(game_id, query.from_user.id)
        except (ValueError, GameError) as exc:
            await _reply_error(query.message, str(exc))
        return

    if len(parts) != 5:
        await query.answer("Ця кнопка вже застаріла.", show_alert=True)
        return

    _, action, raw_game_id, raw_day, phase = parts
    try:
        game_id = int(raw_game_id)
        day_number = int(raw_day)
    except ValueError:
        await query.answer("Некоректна кнопка.", show_alert=True)
        return

    if action == "advance":
        await query.answer("⏭ Завершую етап…")
        try:
            await game_service.advance_phase(
                game_id,
                host_user_id=query.from_user.id,
                expected_day=day_number,
                expected_phase=phase,
            )
        except GameError as exc:
            await _reply_error(query.message, str(exc))
        return

    if action == "extend":
        try:
            await game_service.extend_phase(game_id, query.from_user.id, day_number, phase)
            await query.answer("➕ Додано 60 секунд.")
        except GameError as exc:
            await query.answer(str(exc), show_alert=True)
        return

    if action == "end":
        try:
            game = await game_service.validate_host_phase(
                game_id,
                query.from_user.id,
                day_number,
                phase,
            )
        except GameError as exc:
            await query.answer(str(exc), show_alert=True)
            return
        await query.answer()
        if query.message:
            await query.message.answer(
                "⚠️ <b>Точно завершити поточну ходку?</b>",
                reply_markup=confirm_end_keyboard(game),
            )
        return

    if action == "confirm_end":
        await query.answer("Завершую ходку…")
        try:
            await game_service.end_game(
                game_id,
                query.from_user.id,
                expected_day=day_number,
                expected_phase=phase,
            )
            if query.message:
                try:
                    await query.message.delete()
                except TelegramBadRequest:
                    pass
        except GameError as exc:
            await _reply_error(query.message, str(exc))
        return

    await query.answer("Невідома кнопка.", show_alert=True)
