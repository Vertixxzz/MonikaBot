from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

async def sayori_greeting(message: Message):
    await message.answer(
        "Привеееет! Я Сайори!\n\n"
        "Если я туплю - это не баг, это вертикс ишак ебаный!\n\n"
        "Я только только создаюсь, впереди я выебу еще столько мозгов!",
        parse_mode="Markdown"
    )

def register_greetings(dp: Dispatcher):
    dp.message.register(sayori_greeting, Command(commands=["start"]))

