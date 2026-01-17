from __future__ import annotations
import asyncpg

async def upsert_gacha_menu(pool: asyncpg.Pool, chat_id: int, message_id: int, owner_id: int) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO yuri_gacha_menus(chat_id, message_id, owner_id, used_at)
            VALUES ($1, $2, $3, NULL)
            ON CONFLICT (chat_id, message_id) DO UPDATE
            SET owner_id = EXCLUDED.owner_id,
                created_at = NOW(),
                used_at = NULL
            """,
            chat_id, message_id, owner_id
        )


async def get_gacha_menu_owner(
    pool: asyncpg.Pool,
    chat_id: int,
    message_id: int,
    ttl_minutes: int = 20,
) -> int | None:
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            """
            SELECT owner_id
            FROM yuri_gacha_menus
            WHERE chat_id = $1
              AND message_id = $2
              AND created_at > NOW() - ($3::int * INTERVAL '1 minute')
            """,
            chat_id, message_id, ttl_minutes
        )
    return int(owner) if owner is not None else None

async def cleanup_gacha_menus(
    pool: asyncpg.Pool,
    keep_days: int = 2,
) -> int:
    async with pool.acquire() as conn:
        res = await conn.execute(
            """
            DELETE FROM yuri_gacha_menus
            WHERE created_at < NOW() - ($1::int * INTERVAL '1 day')
            """,
            keep_days
        )
    try:
        return int(res.split()[-1])
    except Exception:
        return 0

async def claim_gacha_menu_roll(
    pool: asyncpg.Pool,
    chat_id: int,
    message_id: int,
    owner_id: int,
    ttl_minutes: int = 20,
) -> bool:
    """
    True -> этот клик первый и меню успешно "захвачено" для крутки
    False -> меню устарело/не твоё/уже обработано (дубль update)
    """
    async with pool.acquire() as conn:
        used = await conn.fetchval(
            """
            UPDATE yuri_gacha_menus
               SET used_at = NOW()
             WHERE chat_id = $1
               AND message_id = $2
               AND owner_id = $3
               AND created_at > NOW() - ($4::int * INTERVAL '1 minute')
               AND used_at IS NULL
             RETURNING used_at
            """,
            chat_id, message_id, owner_id, ttl_minutes
        )
    return used is not None
