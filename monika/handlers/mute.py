from datetime import datetime, timezone

from aiogram import Router
from aiogram.types import ChatPermissions
from aiogram.exceptions import TelegramBadRequest

from common.utils.manage import (
    require_bot_admin,
    resolve_target_user,
    deny_if_self,
    get_args_after_target,
    split_duration_and_tail,
    who_label,
    tg_human_error,
)

router = Router()


@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "мут")
async def mute_handler(message, pool):
    if not await require_bot_admin(pool, message.chat.id, message.from_user.id):
        await message.reply("Ты не админ этого чата!")
        return

    chat_id = message.chat.id
    user_id, display = await resolve_target_user(message, pool, username_pos=1)

    if not user_id:
        await message.answer("Укажи пользователя реплаем или так: `мут @username 15 минут` (время опционально).")
        return

    if await deny_if_self(message, user_id, "замутить"):
        return

    args = get_args_after_target(message, username_pos=1)
    delta, duration_text, _tail = split_duration_and_tail(args)

    until_date = None
    if delta is not None:
        until_date = datetime.now(timezone.utc) + delta

    try:
        await message.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_photos = False,
                can_send_videos = False,
                can_send_audios = False,
                can_send_documents = False,
                can_send_voice_notes = False,
                can_send_video_notes = False,
                can_send_other_messages = False,
                can_add_web_page_previews = False,
            ),
            until_date=until_date,
        )
    except TelegramBadRequest as e:
        await message.answer(tg_human_error(e))
        return

    who = who_label(display)
    if delta is None:
        await message.answer(f"{who} замучен навсегда.")
    else:
        await message.answer(f"{who} замучен на {duration_text}.")

@router.message(lambda msg: msg.text and msg.text.lower().split()[0] in ["размут", "анмут", "говори"])
async def unmute_handler(message, pool):
    if not await require_bot_admin(pool, message.chat.id, message.from_user.id):
        await message.reply("Ты не админ этого чата!")
        return

    chat_id = message.chat.id
    user_id, display = await resolve_target_user(message, pool, username_pos=1)

    if not user_id:
        await message.answer("Укажи пользователя реплаем или так: `размут @username`.")
        return

    if await deny_if_self(message, user_id, "размутить"):
        return

    try:
        await message.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages = True,
                can_send_photos = True,
                can_send_videos = True,
                can_send_audios = True,
                can_send_documents = True,
                can_send_voice_notes = True,
                can_send_video_notes = True,
                can_send_other_messages = True,
                can_add_web_page_previews = True,
        ),
        )
    except TelegramBadRequest as e:
        await message.answer(tg_human_error(e))
        return

    who = who_label(display)
    await message.answer(f"{who} теперь может говорить.")