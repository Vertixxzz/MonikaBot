from datetime import datetime
from zoneinfo import ZoneInfo
MSK = ZoneInfo("Europe/Moscow")

async def db_get_today_phrase(pool, user_id: int):
    sql = """
    SELECT p.id AS phrase_id, p.text
    FROM user_last_day u
    JOIN phrases p ON p.id = u.phrase_id
    WHERE u.user_id = $1
      AND u.last_asked_date_msk = (TIMEZONE('Europe/Moscow', NOW()))::date
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, user_id)
        return (row["phrase_id"], row["text"]) if row else None


async def db_pick_random_phrase(pool):
    sql = "SELECT id AS phrase_id, text FROM phrases ORDER BY random() LIMIT 1"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql)
        if not row:
            raise RuntimeError("Таблица phrases пуста")
        return row["phrase_id"], row["text"]


async def db_save_today_phrase(pool, user_id: int, phrase_id: int):
    sql = """
    INSERT INTO user_last_day (user_id, last_asked_at, last_asked_date_msk, phrase_id)
    VALUES ($1, NOW(), (TIMEZONE('Europe/Moscow', NOW()))::date, $2)
    ON CONFLICT (user_id)
    DO UPDATE SET
      last_asked_at = EXCLUDED.last_asked_at,
      last_asked_date_msk = EXCLUDED.last_asked_date_msk,
      phrase_id = EXCLUDED.phrase_id
    """
    async with pool.acquire() as conn:
        await conn.execute(sql, user_id, phrase_id)