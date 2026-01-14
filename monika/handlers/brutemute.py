from aiogram import Router
from aiogram.types import Message
from cfg import TARGET_USER_ID


router = Router()

@router.message()
async def delete_messages_from_target(message: Message):
    user = message.from_user
    if not user:
        return

    if user.id != TARGET_USER_ID:
        return

    try:
        await message.delete()
    except Exception:
        return