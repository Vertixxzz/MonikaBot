from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from cfg import SAYORITOKEN

sayori_bot = Bot(token=SAYORITOKEN)

async def check_sayori_present(chat_id: int) -> bool:
    try:
        sayori = await sayori_bot.get_chat_member(chat_id, sayori_bot.id)
        if sayori.status in ["member", "administrator", "creator"]:
            return True
        else:
            return False
    except (TelegramForbiddenError, TelegramBadRequest):
        return False