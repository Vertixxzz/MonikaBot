from aiogram import Router, F
from aiogram.types import Message

router = Router()

PREFIX = "О, что это тут?"

@router.message(F.text.startswith(PREFIX))
async def delete_prefixed_messages(message: Message):
    await message.delete()