from aiogram import Router, F
from aiogram.types import Message
from common.db.myday import db_get_today_phrase,db_pick_random_phrase, db_save_today_phrase
router = Router()

@router.message(F.text.func(lambda t: t and t.lower().startswith("моника мой день")))
async def day(message: Message, pool):
    user_id = message.from_user.id

    existing = await db_get_today_phrase(pool, user_id)
    if existing:
        _, text = existing
        await message.reply(f"Ты уже спрашивал сегодня, но твой день пройдет {text}")
        return

    phrase_id, text = await db_pick_random_phrase(pool)

    await message.reply(f"Сегодня твой день пройдёт {text}")

    await db_save_today_phrase(pool, user_id, phrase_id)


