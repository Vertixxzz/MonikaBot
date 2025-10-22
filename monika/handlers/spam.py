import asyncio
from aiogram import Bot, Dispatcher, types, F, Router
from aiogram.types import FSInputFile
from aiogram.enums import ParseMode
from aiogram.utils.markdown import hbold

SEND_INTERVAL_MS = 5

router = Router()

@router.message(F.text.lower() == "беброчка")
async def start_sending_images(message: types.Message, bot: Bot):
    await message.answer(f"{hbold('вы ждали?')}", parse_mode=ParseMode.HTML)
    await asyncio.sleep(3)
    await message.answer(f"{hbold('вот он...лучший апдейт на монику')}", parse_mode=ParseMode.HTML)
    await asyncio.sleep(5)
    await message.answer(f"{hbold('вы готовы?')}", parse_mode=ParseMode.HTML)
    await asyncio.sleep(5)
    await message.answer(f"{hbold('ну что же.. узрите')}", parse_mode=ParseMode.HTML)
    await asyncio.sleep(7)
    while True:
        photo = FSInputFile("common/pictures/image.png")
        await bot.send_photo(chat_id=message.chat.id, photo=photo)
        await asyncio.sleep(SEND_INTERVAL_MS / 1000)
