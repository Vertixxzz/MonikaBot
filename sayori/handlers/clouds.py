from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.filters import Command
from common.utils.ismonikahere import check_monika_present
import random

async def sayori_clouds(message: Message):
    print("считаю облака")
    if not await check_monika_present(message.chat.id):
        await message.answer("Я не могу считать облака без Моники!!")
        return
        print("моники нету!")
    count = random.randint(20, 100)
    lazy = random.randint(1, 10)
    if lazy < 10:
        await message.answer(f"Я вижу... *{count} облаков!*", parse_mode="Markdown")
    else:
        await message.answer("Мне лень считать облака!")

def register_clouds(dp: Dispatcher):
    dp.message.register(sayori_clouds, Command(commands=["clouds"]))
