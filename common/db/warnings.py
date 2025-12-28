from datetime import timedelta

WARN_TTL = timedelta(days=7)

async def add_warning(pool, user_id: int, username: str, chat_id: int, reason: str):
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM warnings WHERE warned_at < now() - interval '7 days'"
        )
        await conn.execute(
            """
            INSERT INTO warnings (user_id, chat_id, username, reason)
            VALUES ($1, $2, $3, $4)
            """,
            user_id, chat_id, username, reason
        )

async def get_warnings(pool, user_id: int, chat_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            WITH fresh AS (
                SELECT *
                FROM warnings
                WHERE user_id = $1
                  AND chat_id = $2
                  AND warned_at >= now() - interval '7 days'
            )
            SELECT
                COUNT(*)::int AS count,
                (SELECT reason FROM fresh ORDER BY warned_at DESC, id DESC LIMIT 1) AS last_reason,
                (SELECT warned_at FROM fresh ORDER BY warned_at DESC, id DESC LIMIT 1) AS last_warned_at
            FROM fresh
            """,
            user_id, chat_id
        )



async def clear_warnings(pool, user_id: int, chat_id: int):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM warnings
            WHERE user_id = $1 AND chat_id = $2
            """,
            user_id, chat_id
        )


async def remove_one_warning(pool, user_id: int, username: str, chat_id: int):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM warnings
            WHERE id = (
                SELECT id
                FROM warnings
                WHERE user_id = $1
                  AND chat_id = $2
                  AND warned_at >= now() - interval '7 days'
                ORDER BY warned_at DESC, id DESC
                LIMIT 1
            )
            """,
            user_id, chat_id
        )


async def get_warning_events(pool, user_id: int, chat_id: int, limit: int = 10):
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT reason, warned_at
            FROM warnings
            WHERE user_id = $1
              AND chat_id = $2
              AND warned_at >= now() - interval '7 days'
            ORDER BY warned_at DESC, id DESC
            LIMIT $3
            """,
            user_id, chat_id, limit
        )
