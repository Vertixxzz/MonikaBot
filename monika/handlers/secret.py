import re
from aiogram import Router, F
from aiogram.types import Message

from cfg import BOOSTERS_LIST, TARGET_CHAT_ID
from common.utils.links import get_bot_in_chat, BotNotFoundError

router = Router()

CODE_TO_BOT = {
    "мон": None,
    "сай": "sai",
    "юри": "yuri",
}


@router.message(F.chat.type == "private", F.text.regexp(r"^(скж)\b", flags=re.IGNORECASE))
async def say_as_bot_handler(message: Message):
    sender = message.from_user
    if not sender:
        return

    if sender.id not in BOOSTERS_LIST:
        return

    text = (message.text or "").strip()

    match = re.match(r"^скж\s+(\S+)\s+([\s\S]+)$", text, flags=re.IGNORECASE)
    if not match:
        await message.answer("Формат: `скж <мон|сай|юри> <текст>`", parse_mode="Markdown")
        return

    code = match.group(1).lower()
    payload = match.group(2).strip()

    if code not in CODE_TO_BOT:
        await message.answer("Доступно только: мон, сай, юри")
        return

    if not payload:
        await message.answer("Нечего отправлять")
        return

    try:
        if code == "мон":
            await message.bot.send_message(TARGET_CHAT_ID, payload)
            await message.answer("Отправлено от моего Имени")
            return

        bot_name = CODE_TO_BOT[code]
        target_bot = await get_bot_in_chat(bot_name, TARGET_CHAT_ID)
        await target_bot.send_message(TARGET_CHAT_ID, payload)

        await message.answer(f"Отправлено от имени {code}")

    except BotNotFoundError as e:
        await message.answer(f"Бот недоступен: {e}")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")
