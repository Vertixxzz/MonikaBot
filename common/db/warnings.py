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