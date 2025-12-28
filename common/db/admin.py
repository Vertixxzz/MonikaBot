from typing import Iterable

async def get_bot_level(pool, chat_id: int, user_id: int) -> int | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT level FROM bot_admins WHERE chat_id=$1 AND user_id=$2",
            chat_id, user_id
        )
        return int(row["level"]) if row else None


async def upsert_bot_level(pool, chat_id: int, user_id: int, level: int, assigned_by: int | None) -> None:
    if not (1 <= level <= 5):
        raise ValueError("level must be between 1 and 5")
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO bot_admins (chat_id, user_id, level, assigned_by)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (chat_id, user_id)
            DO UPDATE SET
                level = EXCLUDED.level,
                assigned_by = EXCLUDED.assigned_by,
                assigned_at = NOW()
            """,
            chat_id, user_id, level, assigned_by
        )


async def remove_bot_admin(pool, chat_id: int, user_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM bot_admins WHERE chat_id=$1 AND user_id=$2",
            chat_id, user_id
        )


async def list_bot_admins(pool, chat_id: int, min_level: int = 1) -> list[tuple[int, int]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT user_id, level
            FROM bot_admins
            WHERE chat_id=$1 AND level >= $2
            ORDER BY level DESC, assigned_at DESC
            """,
            chat_id, min_level
        )
        return [(int(r["user_id"]), int(r["level"])) for r in rows]
