from aiogram import F, Router
from aiogram.types import Message

router = Router()

@router.message(F.text.func(lambda t: t and t.lower().startswith(("/бонус", "/bonus"))))
async def garem(message: Message):
    await message.reply("гаремник in the big 25😭🙏, но я так же дам тебе докидолларов")
