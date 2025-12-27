from aiogram import Router, F, types
from datetime import date

router = Router()


@router.message(F.text.casefold().in_(["моника стата","стата"]))
async def stats_today(message: types.Message, pool):
    chat_id = message.chat.id
    today = date.today()

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT username, user_id, messages_today
            FROM user_stats
            WHERE chat_id = $1 AND last_message_date = $2
            ORDER BY messages_today DESC
            LIMIT 20
        """, chat_id, today)

    if not rows:
        await message.reply("Сегодня ещё никто не писал сообщений!")
        return

    total_today = sum(r["messages_today"] for r in rows)
    text = "\n".join(
        f"{i+1}. {r['username'] or 'Безымянный'} — {r['messages_today']} соо"
        for i, r in enumerate(rows)
    )
    text += f"\n\nВсего — {total_today} соо"
    await message.reply(text)


@router.message(F.text.lower() == "моника стата вся")
async def stats_all(message: types.Message, pool):
    chat_id = message.chat.id

    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT username, user_id, messages_total
            FROM user_stats
            WHERE chat_id = $1
            ORDER BY messages_total DESC
            LIMIT 20
        """, chat_id)

    if not rows:
        await message.reply("Пока что нет статистики.")
        return

    total_all = sum(r["messages_total"] for r in rows)
    text = "\n".join(
        f"{i+1}. {r['username'] or 'Безымянный'} — {r['messages_total']} соо"
        for i, r in enumerate(rows)
    )
    text += f"\n\nВсего — {total_all} соо"
    await message.reply(text)


