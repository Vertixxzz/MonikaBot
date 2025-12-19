#NOT USED RN

from cfg import DB_SCHEMA
import asyncpg

async def get_user_clan(pool, user_id: int):
    query = """
        SELECT clan_id, role 
        FROM clan_members 
        WHERE user_id = $1
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, user_id)
    return row


async def create_clan(pool, user_id: int, name: str, chat_id: int):
    async with pool.acquire() as conn:
        async with conn.transaction():
            clan_id = await conn.fetchval("""
                INSERT INTO clans (name, leader_id, chat_id)
                VALUES ($1, $2, $3)
                RETURNING id
            """, name, user_id, chat_id)

            await conn.execute("""
                INSERT INTO clan_members (user_id, clan_id, role)
                VALUES ($1, $2, 'leader')
            """, user_id, clan_id)

            return clan_id

async def get_clan(pool, clan_id: int):
    query = "SELECT * FROM clans WHERE id = $1"
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, clan_id)

async def get_member_count(pool, clan_id: int):
    query = "SELECT COUNT(*) FROM clan_members WHERE clan_id = $1"
    async with pool.acquire() as conn:
        return await conn.fetchval(query, clan_id)

async def join_clan(pool, user_id: int, clan_id: int, chat_id: int):
    async with pool.acquire() as conn:
        async with conn.transaction():

            row = await conn.fetchrow("""
                SELECT clan_id FROM clan_members 
                WHERE user_id = $1
            """, user_id)

            if row:
                return {"ok": False, "reason": "already_in_clan"}

            clan = await conn.fetchrow("""
                SELECT chat_id FROM clans WHERE id = $1
            """, clan_id)

            if not clan:
                return {"ok": False, "reason": "not_found"}

            if clan["chat_id"] != chat_id:
                return {"ok": False, "reason": "wrong_chat"}

            count = await conn.fetchval("""
                SELECT COUNT(*) FROM clan_members WHERE clan_id = $1
            """, clan_id)

            if count >= 10:
                return {"ok": False, "reason": "clan_full"}

            await conn.execute("""
                INSERT INTO clan_members (user_id, clan_id, role)
                VALUES ($1, $2, 'member')
            """, user_id, clan_id)

            return {"ok": True}

async def get_next_leader(pool, clan_id: int):
    query = """
        SELECT user_id 
        FROM clan_members 
        WHERE clan_id = $1 AND role = 'member'
        ORDER BY joined_at ASC
        LIMIT 1
    """
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, clan_id)


async def delete_clan(pool, clan_id: int):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM clan_members WHERE clan_id = $1", clan_id)
            await conn.execute("DELETE FROM clans WHERE id = $1", clan_id)

async def leave_clan(pool, user_id: int, successor_id: int | None = None):
    async with pool.acquire() as conn:
        async with conn.transaction():

            member = await conn.fetchrow("""
                SELECT clan_id, role 
                FROM clan_members 
                WHERE user_id = $1
            """, user_id)

            if not member:
                return {"ok": False, "reason": "not_in_clan"}

            clan_id = member["clan_id"]

            if member["role"] == "member":
                await conn.execute("DELETE FROM clan_members WHERE user_id = $1", user_id)
                return {"ok": True, "leader_changed": False}

            next_leader = None

            if successor_id is not None:
                next_leader = await conn.fetchrow("""
                    SELECT user_id FROM clan_members 
                    WHERE user_id = $1 AND clan_id = $2 AND role = 'member'
                """, successor_id, clan_id)
            else:
                next_leader = await conn.fetchrow("""
                    SELECT user_id 
                    FROM clan_members 
                    WHERE clan_id = $1 AND role = 'member'
                    ORDER BY joined_at ASC
                    LIMIT 1
                """, clan_id)

            if not next_leader:
                await delete_clan(conn, clan_id)
                return {"ok": True, "leader_changed": False, "clan_deleted": True}

            new_leader_id = next_leader["user_id"]

            await conn.execute("""
                UPDATE clan_members 
                SET role='leader' 
                WHERE user_id = $1
            """, new_leader_id)

            await conn.execute("""
                DELETE FROM clan_members WHERE user_id = $1
            """, user_id)

            await conn.execute("""
                UPDATE clans SET leader_id = $1 WHERE id = $2
            """, new_leader_id, clan_id)

            return {"ok": True, "leader_changed": True, "new_leader": new_leader_id}

async def get_clan_by_name(pool, name: str):
    query = "SELECT * FROM clans WHERE lower(name) = lower($1)"
    async with pool.acquire() as conn:
        return await conn.fetchrow(query, name)
