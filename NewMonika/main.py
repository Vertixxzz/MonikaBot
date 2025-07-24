from aiogram.types import BufferedInputFile
from aiogram import Dispatcher, F
from aiogram.types import Message
from cfg import *
import asyncio
from monika.register import register_monika_handlers
from sayori.register import register_sayori_handlers
from NewMonika.common.utils.db import connect_db
from monika.middlewares.pool import PoolMiddleware

monika_bot = Bot(token=MONIKATOKEN)
sayori_bot = Bot(token=SAYORITOKEN)
monika_dp = Dispatcher()
sayori_dp = Dispatcher()

register_monika_handlers(monika_dp)
print("Моника запущена")
register_sayori_handlers(sayori_dp)
print("Сайори запущена")

async def send_console_messages():
    loop = asyncio.get_running_loop()
    while True:
        message = await loop.run_in_executor(None, input, "Введите сообщение для отправки в группу: ")
        if message.lower() in ["exit", "quit"]:
            print("Завершаем отправку сообщений.")
            break
        try:
            await monika_bot.send_message(chat_id=TARGET_CHAT_ID, text=message)
            print("Сообщение отправлено:")
        except Exception as e:
            print(f"Ошибка при отправке сообщения: {e}")

async def main():
    pool = await connect_db()
    monika_dp.update.outer_middleware(PoolMiddleware(pool))
    console_task = asyncio.create_task(send_console_messages())
    await asyncio.gather(
        monika_dp.start_polling(monika_bot),
        sayori_dp.start_polling(sayori_bot),
        console_task
    )

if __name__ == "__main__":
    asyncio.run(main())