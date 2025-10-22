from aiogram import Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

async def monika_greeting(message: Message):
    await message.answer(
        "Привеееет! Я Моника!\n\n"
        "Если я туплю - это не баг, это мой создатели олень!\n\n"
        "Я только только создаюсь, впереди нас ждет очень много крутого",
        parse_mode="Markdown"
    )

def register_greetings(dp: Dispatcher):
    dp.message.register(monika_greeting, Command(commands=["start"]))