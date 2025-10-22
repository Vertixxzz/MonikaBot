
from __future__ import annotations
import datetime
from typing import Optional

async def create_duel(pool, *, chat_id: int, message_id: int,
                      initiator_id: int, initiator_username: str,
                      opponent_id: int, opponent_username: str,
                      ttl_seconds: int = 3600):
    expires_at = datetime.datetime.utcnow() + datetime.timedelta(seconds=ttl_seconds)
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO duels (chat_id, message_id,
                               initiator_id, initiator_username,
                               opponent_id, opponent_username,
                               status, turn, expires_at)
            VALUES ($1,$2,$3,$4,$5,$6,'pending',$3,$7)
            ON CONFLICT (chat_id, message_id) DO UPDATE
              SET initiator_id = EXCLUDED.initiator_id,
                  initiator_username = EXCLUDED.initiator_username,
                  opponent_id = EXCLUDED.opponent_id,
                  opponent_username = EXCLUDED.opponent_username,
                  status = 'pending',
                  turn = EXCLUDED.turn,
                  expires_at = EXCLUDED.expires_at
        """, chat_id, message_id,
             initiator_id, initiator_username,
             opponent_id, opponent_username,
             expires_at)

async def get_duel(pool, chat_id: int, message_id: int) -> Optional[dict]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT chat_id, message_id,
                   initiator_id, initiator_username,
                   opponent_id, opponent_username,
                   status, turn, created_at, expires_at
            FROM duels
            WHERE chat_id=$1 AND message_id=$2
        """, chat_id, message_id)
        return dict(row) if row else None

async def delete_duel(pool, chat_id: int, message_id: int):
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM duels WHERE chat_id=$1 AND message_id=$2",
                           chat_id, message_id)

async def set_status(pool, chat_id: int, message_id: int, status: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE duels SET status=$3 WHERE chat_id=$1 AND message_id=$2
        """, chat_id, message_id, status)

async def set_turn(pool, chat_id: int, message_id: int, turn_user_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE duels SET turn=$3 WHERE chat_id=$1 AND message_id=$2
        """, chat_id, message_id, turn_user_id)
