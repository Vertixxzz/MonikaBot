from aiogram import Router, F
from aiogram.types import Message
from common.utils.links import get_bot
from common.utils.isshehere import check_sayori_present
import asyncio

router = Router()

@router.message(F.text.lower().in_({"обнял", "обняла", "обнять"}))
async def monika_hug(message: Message):
    if not message.reply_to_message:
        return

    reply_from = (
        message.reply_to_message.from_user
        or message.reply_to_message.sender_chat
    )
    if not reply_from:
        return

    monika_info = await message.bot.get_me()
    if reply_from.id != monika_info.id:
        return

    sender = message.from_user
    if not sender:
        return

    name = sender.username or sender.first_name
    chat_id = message.chat.id

    await asyncio.sleep(1)

    sayori = get_bot("sayori")
    if sayori and await check_sayori_present(chat_id):
        try:
            await sayori.send_message(chat_id, f"{name} обнял(а) Монику!")
        except Exception as e:
            print("Не удалось отправить сообщение от Сайори:", e)

    await message.answer("наконец-то моя очередь!")
