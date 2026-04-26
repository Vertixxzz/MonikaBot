from aiogram import Router
from aiogram.exceptions import TelegramBadRequest

from common.utils.manage import (
    require_bot_admin,
    resolve_target_user,
    deny_if_self,
    who_label,
    tg_human_error,
)

router = Router()


@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "кик")
async def kick_handler(message, pool):
    if not await require_bot_admin(pool, message.chat.id, message.from_user.id):
        message.reply("Ты не админ этого чата!")
        return

    chat_id = message.chat.id
    user_id, display = await resolve_target_user(message, pool, username_pos=1)

    if not user_id:
        await message.answer("Укажи пользователя реплаем или так: `кик @username`.")
        return

    if await deny_if_self(message, user_id, "кикнуть"):
        return

    try:
        await message.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        await message.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
    except TelegramBadRequest as e:
        await message.answer(tg_human_error(e))
        return

    await message.answer(f"{who_label(display)} кикнут.")