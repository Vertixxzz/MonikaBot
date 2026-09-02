from __future__ import annotations

from asyncpg import pool


async def get_lootbox_inventory(pool, chat_id: int, user_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT lootboxes,keys
            FROM lootbox_inventory
            WHERE chat_id = $1 AND user_id = $2
            """, chat_id, user_id
        )
        return row["lootboxes"], row["keys"] if row else (0,0)

async def add_key(pool, user_id:int, chat_id:int, amount:int = 1):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO lootbox_inventory (user_id, chat_id,keys)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, chat_id)
            DO UPDATE SET
                keys = lootbox_inventory.keys + EXCLUDED.keys
            """, user_id, chat_id, amount
        )

async def add_box(pool, user_id:int, chat_id:int, amount:int = 1):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO lootbox_inventory (user_id, chat_id,lootboxes)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, chat_id)
            DO UPDATE SET
                lootboxes = lootbox_inventory.lootboxes + EXCLUDED.lootboxes
            """, user_id, chat_id, amount
        )

async def open_lootbox(pool, user_id:int, chat_id:int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE lootbox_inventory
            SET 
                lootboxes = lootboxes - 1,
                keys = keys - 1
            WHERE user_id = $1 AND chat_id = $2 AND keys > 0 AND lootboxes > 0
            RETURNING lootboxes, keys
            """, user_id, chat_id
        )
        return row if row else None