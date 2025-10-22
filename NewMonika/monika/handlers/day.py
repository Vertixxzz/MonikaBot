from aiogram import Router, F
from aiogram.types import Message
from common.utils.db import db_get_today_phrase,db_pick_random_phrase, db_save_today_phrase
router = Router()

@router.message(F.text.func(lambda t: t and t.lower().startswith("моника мой день")))
async def day(message: Message, pool):
    user_id = message.from_user.id

    # 1) пробуем достать «сегодняшнюю» фразу из БД
    existing = await db_get_today_phrase(pool, user_id)
    if existing:
        _, text = existing
        await message.reply(f"Ты уже спрашивал сегодня, но твой день пройдет {text}")
        return

    # 2) выбираем новую случайную фразу из БД
    phrase_id, text = await db_pick_random_phrase(pool)

    # 3) отвечаем
    await message.reply(f"Сегодня твой день пройдёт {text}")

    # 4) сохраняем «что выпало сегодня»
    await db_save_today_phrase(pool, user_id, phrase_id)


