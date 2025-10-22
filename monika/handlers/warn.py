from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.utils.markdown import hbold
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from common.utils.db import add_warning, get_warnings, clear_warnings, get_user_id_by_username
from common.utils.db import remove_one_warning
from aiogram.types import ChatPermissions


user_idd = 0
router = Router()

@router.message(lambda msg: msg.text and msg.text.lower().split()[0:2] == ["моника", "варн"])
async def warn_user_handler(message: Message, pool):
    chat_id = message.chat.id
    lines = message.text.splitlines()
    if message.reply_to_message:
        warned_user = message.reply_to_message.from_user
        target_id = warned_user.id
        username = warned_user.username or warned_user.full_name
        target_member = await message.bot.get_chat_member(chat_id, target_id)
    else:

        parts = lines[0].split()
        if len(parts) < 3:
            await message.answer("Пожалуйста, укажи имя юзера в своем сообщении")
            return

        username = parts[2].lstrip('@')
        target_id = await get_user_id_by_username(pool, username, chat_id)

        print(username)

        if not target_id:
            await message.answer("Не удалось найти пользователя.")
            return


    sender_id = message.from_user.id
    sender_member = await message.bot.get_chat_member(chat_id, sender_id)

    if sender_member.status not in ("administrator", "creator"):
        await message.answer("Нужны права администратора для выдачи варнов")
        return
    try:
        reason = lines[1].strip()
    except IndexError:
        reason = "нарушение правил"

    await add_warning(pool, target_id, username, chat_id, reason)
    data = await get_warnings(pool, target_id, chat_id)
    count = data["count"]

    if count >= 3:
        try:
            await message.bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
            await clear_warnings(pool, target_id, chat_id)
            await message.answer(
                f"@{username} получил 3 предупреждения и был забанен.\n"
                f"Причина последнего нарушения: {reason}"
            )
        except TelegramBadRequest:
            await message.answer("Я не могу забанить этого пользователя. У меня нет таких прав.")
            await clear_warnings(pool, target_id, chat_id)
    else:
        await message.answer(
            f"@{username} получил предупреждение.\n"
            f"Причина: {reason}\n"
            f"Всего предупреждений: {count}/3"
        )

        print(reason)


@router.message(F.text.lower().startswith("моника снять варн"))
async def warn_user_snyat(message: Message, pool):
    chat_id = message.chat.id

    if message.reply_to_message:
        unwarned_user = message.reply_to_message.from_user
        user_id = unwarned_user.id
        username = unwarned_user.username or unwarned_user.full_name
    else:
        username = message.text[18:].strip().lstrip('@')
        user_id = await get_user_id_by_username(pool, username, chat_id)

        if not user_id:
            await message.answer("Не удалось найти пользователя.")
            return

    sender_id = message.from_user.id
    sender_member = await message.bot.get_chat_member(chat_id, sender_id)

    if sender_member.status not in ("administrator", "creator"):
        await message.answer("нужны права администратора для снятия варнов")
        return

    data = await get_warnings(pool, user_id, chat_id)

    if not data or data['count'] == 0:
        await message.answer("У данного пользователя нет варнов.")
        return

    await remove_one_warning(pool, user_id, username, chat_id)
    await message.answer(f"С пользователя @{username} был снят 1 варн")


@router.message(lambda msg: msg.text and msg.text.lower().split()[0:2] == ["моника", "варны"])
async def showwarn_handler(message: Message, pool):
    if message.reply_to_message:
        unwarned_user = message.reply_to_message.from_user
        user_id = unwarned_user.id
        chat_id = message.chat.id
        username = unwarned_user.username or unwarned_user.full_name
        data = await get_warnings(pool, user_id, chat_id)
    else:
        chat_id = message.chat.id
        username = message.text[13:].strip().lstrip('@')
        print(username)
        user_id = await get_user_id_by_username(pool, username, chat_id)
        data = await get_warnings(pool, user_id, chat_id)

        if not user_id:
            await message.answer("Не удалось найти пользователя.")
            return

    if not data or data['count'] == 0:
        await message.answer("У данного пользователя нет варнов.")
        return

    count = data['count']

    await message.answer(f"у пользователя @{username} есть {count} варнов")

@router.message(lambda msg: msg.text and msg.text.lower().split()[0:2] == ["моника", "мут"])
async def mute_handler(message: Message, pool):
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
        chat_id = message.chat.id
    else:
        chat_id = message.chat.id
        user_id = await get_user_id_by_username(pool, message.from_user.username, chat_id)
        if not user_id or user_id == None:
            await message.answer("Не удалось найти такого пользователя")
    await message.bot.restrict_chat_member(
        chat_id,
        user_id,
        permissions=ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False
        )
    )
    await message.answer(f"замутили хаха ботик ")



