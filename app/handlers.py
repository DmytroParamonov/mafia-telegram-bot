from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.types import CallbackQuery, Message

from app.keyboards import confirm_end_keyboard
from app.service import GameError, GameService

router = Router()


async def _reply_error(message: Message | None, text: str) -> None:
    if message is not None:
        await message.answer(f"⚠️ {text}")


@router.message(CommandStart())
async def start_command(
    message: Message,
    command: CommandObject,
    game_service: GameService,
) -> None:
    if message.from_user is None:
        return
    await game_service.ensure_user(message.from_user)

    payload = command.args or ""
    if payload.startswith("join_"):
        try:
            game_id = int(payload.removeprefix("join_"))
            joined = await game_service.join_game(game_id, message.from_user)
        except (ValueError, GameError) as exc:
            await message.answer(f"⚠️ Не удалось войти в игру: {exc}")
            return

        if joined:
            await message.answer(
                "✅ <b>Ты в игре!</b>\n\n"
                "Когда хост закроет набор, роль придёт сюда. Не удаляй и не блокируй бота до конца партии."
            )
        else:
            await message.answer("✅ Ты уже находишься в этом лобби.")
        return

    await message.answer(
        "🎭 <b>Мафия</b>\n\n"
        "Я могу полностью вести игру: раздать роли, провести ночь, собрать тайные действия и голосование.\n\n"
        "Чтобы начать новую партию, добавь меня в групповой чат и напиши там /mafia."
    )


@router.message(Command("mafia"))
async def mafia_command(message: Message, game_service: GameService) -> None:
    if message.chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP}:
        await message.answer("🎭 Новую игру нужно создавать в групповом чате командой /mafia.")
        return
    if message.from_user is None:
        await message.answer("⚠️ Не могу определить создателя игры. Отключи анонимный режим администратора.")
        return

    try:
        await game_service.create_lobby(message.chat.id, message.chat.title, message.from_user)
    except GameError as exc:
        await message.answer(f"⚠️ {exc}")


@router.message(Command("help"))
async def help_command(message: Message) -> None:
    await message.answer(
        "🎭 <b>Как играть</b>\n\n"
        "1. В группе: /mafia\n"
        "2. Все игроки жмут «➕ Войти в игру» и подтверждают вход в личке.\n"
        "3. Хост настраивает роли и жмёт «🚀 Игроки набраны».\n"
        "4. Секретные роли, ночные действия и бюллетени приходят каждому лично.\n"
        "5. Бот сам меняет фазы и определяет победителя.\n\n"
        "Команда /stats показывает твою статистику."
    )


@router.message(Command("stats"))
async def stats_command(message: Message, game_service: GameService) -> None:
    if message.from_user is None:
        return
    await message.answer(await game_service.stats_text(message.from_user.id))


@router.callback_query(F.data.startswith("l:"))
async def lobby_callback(query: CallbackQuery, game_service: GameService) -> None:
    if query.from_user is None or not query.data:
        return
    parts = query.data.split(":")
    if len(parts) != 3:
        await query.answer("Некорректная кнопка.", show_alert=True)
        return
    _, action, raw_game_id = parts
    try:
        game_id = int(raw_game_id)
    except ValueError:
        await query.answer("Некорректная игра.", show_alert=True)
        return

    if action == "start":
        await query.answer("🚀 Запускаю игру…")
        try:
            await game_service.start_game(game_id, query.from_user.id)
        except GameError as exc:
            await _reply_error(query.message, str(exc))
        return

    try:
        if action == "leave":
            await game_service.leave_game(game_id, query.from_user.id)
            await query.answer("Ты вышел из лобби.")
        elif action.startswith("toggle_"):
            await game_service.toggle_setting(game_id, query.from_user.id, action)
            await query.answer("Настройка изменена.")
        elif action == "cancel":
            await game_service.cancel_lobby(game_id, query.from_user.id)
            await query.answer("Лобби отменено.")
        else:
            await query.answer("Неизвестная кнопка.", show_alert=True)
    except GameError as exc:
        await query.answer(str(exc), show_alert=True)


@router.callback_query(F.data.startswith("a:"))
async def night_action_callback(query: CallbackQuery, game_service: GameService) -> None:
    if query.from_user is None or not query.data:
        return
    parts = query.data.split(":")
    if len(parts) != 5:
        await query.answer("Некорректная кнопка.", show_alert=True)
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

    await query.answer("Выбор принят.")
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
async def vote_callback(query: CallbackQuery, game_service: GameService) -> None:
    if query.from_user is None or not query.data:
        return
    parts = query.data.split(":")
    if len(parts) != 5:
        await query.answer("Некорректная кнопка.", show_alert=True)
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

    await query.answer("Голос принят.")
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
async def host_callback(query: CallbackQuery, game_service: GameService) -> None:
    if query.from_user is None or not query.data:
        return
    parts = query.data.split(":")
    action = parts[1] if len(parts) >= 2 else ""

    if action == "dismiss" and len(parts) == 3:
        await query.answer("Отменено.")
        if query.message:
            try:
                await query.message.delete()
            except TelegramBadRequest:
                pass
        return

    if action == "rematch" and len(parts) == 3:
        try:
            game_id = int(parts[2])
            await query.answer("🔄 Создаю реванш…")
            await game_service.rematch(game_id, query.from_user.id)
        except (ValueError, GameError) as exc:
            await _reply_error(query.message, str(exc))
        return

    if len(parts) != 5:
        await query.answer("Эта кнопка устарела.", show_alert=True)
        return

    _, action, raw_game_id, raw_day, phase = parts
    try:
        game_id = int(raw_game_id)
        day_number = int(raw_day)
    except ValueError:
        await query.answer("Некорректная кнопка.", show_alert=True)
        return

    if action == "advance":
        await query.answer("⏭ Завершаю фазу…")
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
                "⚠️ <b>Точно завершить текущую игру?</b>",
                reply_markup=confirm_end_keyboard(game),
            )
        return

    if action == "confirm_end":
        await query.answer("Останавливаю игру…")
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

    await query.answer("Неизвестная кнопка.", show_alert=True)
