from datetime import datetime, timezone

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest

from common.utils.manage import (
    require_bot_admin,
    resolve_target_user,
    deny_if_self,
    get_args_after_target,
    split_duration_and_tail,
    extract_reason,
    who_label,
    tg_human_error,
)

router = Router()


@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "бан")
async def ban_handler(message, pool):
    if not await require_bot_admin(pool, message.chat.id, message.from_user.id):
        await message.reply("Ты не админ этого чата!")
        return

    chat_id = message.chat.id
    user_id, display = await resolve_target_user(message, pool, username_pos=1)

    if not user_id:
        await message.answer("Укажи пользователя реплаем или так: `бан @username 7д` (время опционально).")
        return

    if await deny_if_self(message, user_id, "забанить"):
        return

    args = get_args_after_target(message, username_pos=1)
    delta, duration_text, tail = split_duration_and_tail(args)
    reason = extract_reason(message, inline_tail=tail)

    until_date = None
    if delta is not None:
        until_date = datetime.now(timezone.utc) + delta

    try:
        await message.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            until_date=until_date,
        )
    except TelegramBadRequest as e:
        await message.answer(tg_human_error(e))
        return

    who = who_label(display)
    if delta is None:
        if reason:
            await message.answer(f"{who} забанен.\nПричина: {reason}")
        else:
            await message.answer(f"{who} забанен.")
    else:
        if reason:
            await message.answer(f"{who} забанен на {duration_text}.\nПричина: {reason}")
        else:
            await message.answer(f"{who} забанен на {duration_text}.")


@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "разбан")
async def unban_handler(message, pool):
    if not await require_bot_admin(pool, message.chat.id, message.from_user.id):
        message.reply("Ты не админ этого чата!")
        return

    chat_id = message.chat.id
    user_id, display = await resolve_target_user(message, pool, username_pos=1)

    if not user_id:
        await message.answer("Укажи пользователя реплаем или так: `разбан @username`.")
        return

    try:
        await message.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
    except TelegramBadRequest as e:
        await message.answer(tg_human_error(e))
        return

    await message.answer(f"{who_label(display)} разбанен.")