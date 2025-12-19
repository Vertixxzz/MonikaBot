from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from datetime import datetime, timedelta
import asyncio
import random

router = Router()

TIMEOUT = 300
PIC_CHANCE = 0.1
CHANCE = 0.3

hushphoto = FSInputFile("common/pictures/hush.png")

random_messages = [
    "А... а почему все молчат?",
    "Тишина такая, что я слышу собственные мысли",
    "Эй, ребят, вы живы?",
    "Неужели я удалила лишний файл?",
    "Чат спит? Или я просто скучаю?",
    "Тут слишком тихо... подозрительно тихо",
    "Ну хоть кто-нибудь скажите 'привет'",
    "Кажется, я слышу сверчков",
    "А.. А почему все молчат?",
]

last_message_time = {}
silence_tasks = {}


async def check_silence(chat_id: int, bot):
    while True:
        await asyncio.sleep(5)
        last_time = last_message_time.get(chat_id)
        if not last_time:
            continue

        now = datetime.utcnow()
        if now - last_time > timedelta(seconds=TIMEOUT):
            print(f"Слишком тихо в чате {chat_id}")

            if random.random() < CHANCE:
                if random.random() < PIC_CHANCE:
                    await bot.send_photo(chat_id, hushphoto)
                else:
                    msg = random.choice(random_messages)
                    await bot.send_message(chat_id, msg)

            last_message_time[chat_id] = datetime.utcnow()


@router.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: Message):
    chat_id = message.chat.id
    last_message_time[chat_id] = datetime.utcnow()

    if chat_id not in silence_tasks:
        print(f"Начинаю следить за чатом {chat_id}")
        silence_tasks[chat_id] = asyncio.create_task(
            check_silence(chat_id, message.bot)
        )



