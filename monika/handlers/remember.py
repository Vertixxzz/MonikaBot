import re
from aiogram import Router, F
from aiogram.types import Message
from common.db.advice import save_advice, get_random_advice

router = Router()

@router.message(F.text.regexp(r"(?i)^моника запомни\s+(.+)"))
async def monika_remember(message: Message, **data):
    match = re.match(r"(?i)^моника запомни\s+(.+)", message.text)
    if not match:
        await message.reply("Что именно мне запомнить?")
        return

    content = match.group(1).strip()

    pool = data["pool"]

    await save_advice(
        pool,
        user_id=message.from_user.id,
        username=message.from_user.username or "unknown",
        chat_id=message.chat.id,
        content=content
    )

    await message.reply(f"Запомнила: {content}")

@router.message(F.text.lower() == "моника покажи")
async def monika_show(message: Message, **data):
    pool = data["pool"]
    advice = await get_random_advice(pool)

    if advice:
        await message.reply(f" Совет: *{advice}*", parse_mode="Markdown")
    else:
        await message.reply("У меня пока нет ни одного совета... 🥲")
