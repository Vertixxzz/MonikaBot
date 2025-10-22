from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from cfg import bot
import random

router = Router()

@router.message(F.text.regexp(r"(?i)^дыньки$"))
async def send_dinki(message: Message):
    await message.reply("дыньки")
    photo1 = FSInputFile("common/pictures/dinkijpg.jpg")
    photo2 = FSInputFile("common/pictures/dinki.jpg")
    rand = random.randint(1, 2)
    if rand == 1:
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=photo1,
            reply_to_message_id=message.message_id
        )
    else:
        await bot.send_photo(
            chat_id=message.chat.id,
            photo=photo2,
            reply_to_message_id=message.message_id
        )
