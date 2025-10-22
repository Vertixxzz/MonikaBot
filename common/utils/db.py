import asyncpg
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
MSK = ZoneInfo("Europe/Moscow")
db_pool = None

async def connect_db():
    return await asyncpg.create_pool(
        user='postgres',
        password='123',
        database='postgres',
        host='127.0.0.1',
        port=5432
    )

async def save_advice(pool, user_id: int, username: str, chat_id: int, content: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO advices (user_id, username, chat_id, content)
            VALUES ($1, $2, $3, $4)
            """,
            user_id, username, chat_id, content
        )

async def get_random_advice(pool):
    async with pool.acquire() as conn:
        result = await conn.fetchrow("SELECT content FROM advices ORDER BY random() LIMIT 1;")
        return result["content"] if result else None

# common/db.py

async def get_balance(pool, user_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT balance FROM wallets WHERE user_id = $1", user_id
        )
        return row["balance"] if row else 0

async def add_balance(pool, user_id, username, amount):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO wallets (user_id, username, balance)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id)
            DO UPDATE SET balance = wallets.balance + $3, updated_at = now()
        """, user_id, username, amount)

async def set_balance(pool, user_id, amount):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO wallets (user_id, balance)
            VALUES ($1, $2)
            ON CONFLICT (user_id)
            DO UPDATE SET balance = $2, updated_at = now()
        """, user_id, amount)


async def add_warning(pool, user_id: int, username: str, chat_id: int, reason: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO warnings (user_id, chat_id, username, count, last_reason)
            VALUES ($1, $2, $3, 1, $4)
            ON CONFLICT (user_id, chat_id)
            DO UPDATE SET 
                count = warnings.count + 1,
                username = EXCLUDED.username,
                last_reason = EXCLUDED.last_reason,
                last_warned_at = now()
        """, user_id, chat_id, username, reason)

async def get_warnings(pool, user_id: int, chat_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT count, last_reason, last_warned_at
            FROM warnings
            WHERE user_id = $1 AND chat_id = $2
        """, user_id, chat_id)
        return row

async def clear_warnings(pool, user_id: int, chat_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM warnings
            WHERE user_id = $1 AND chat_id = $2
        """, user_id, chat_id)

async def remove_one_warning(pool, user_id: int, username: str, chat_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO warnings (user_id, chat_id, username, count)
            VALUES ($1, $2, $3, 0)
            ON CONFLICT (user_id, chat_id)
            DO UPDATE SET 
                count = CASE 
                    WHEN warnings.count > 0 THEN warnings.count - 1 
                    ELSE 0 
                END,
                username = EXCLUDED.username,
                last_reason = EXCLUDED.last_reason,
                last_warned_at = now()
        """, user_id, chat_id, username)

async def get_user_id_by_username(pool, username: str, chat_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT user_id FROM wallets WHERE username = $1 AND chat_id = $2
        """, username, chat_id)
        return row["user_id"] if row else None

async def drink_beer(pool, user_id: int, chat_id: int, beer_amount: float):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO beer_stats (user_id, chat_id, amount)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, chat_id)
            DO UPDATE SET
                amount = beer_stats.amount + EXCLUDED.amount,
                updated_at = now()
            """,
            user_id,
            chat_id,
            beer_amount,
        )

# лучше назвать явно: get_beer_amount
async def get_beer(pool, user_id: int, chat_id: int) -> float:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT amount FROM beer_stats WHERE user_id = $1 AND chat_id = $2",
            user_id, chat_id
        )
        # asyncpg может вернуть Decimal/None — приводим к float
        return float(row["amount"]) if row and row["amount"] is not None else 0.0

async def db_get_today_phrase(pool, user_id: int):
    """
    Вернёт (phrase_id, text) если сегодня по МСК уже спрашивал, иначе None.
    """
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
    """
    Выбирает (phrase_id, text) случайной фразы из таблицы phrases.
    """
    sql = "SELECT id AS phrase_id, text FROM phrases ORDER BY random() LIMIT 1"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql)
        if not row:
            raise RuntimeError("Таблица phrases пуста")
        return row["phrase_id"], row["text"]


async def db_save_today_phrase(pool, user_id: int, phrase_id: int):
    """
    Сохраняет как «сегодняшнюю по МСК» (upsert).
    """
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