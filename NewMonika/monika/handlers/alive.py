from aiogram import Router, F
from aiogram.types import Message

router = Router()

@router.message(F.text.lower() == "ты жива?")
async def alive(message: Message):
    await message.reply("да вертекс я жива")