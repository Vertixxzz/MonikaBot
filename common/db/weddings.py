from __future__ import annotations

from datetime import datetime
from typing import Optional, Dict, Any

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

async def db_get_marriage_by_user(pool, user_id: int) -> Optional[Dict[str, Any]]:
    sql = """
        SELECT w.user1_id, w.user2_id, w.created_at
        FROM wedding_members m
        JOIN weddings w ON w.id = m.wedding_id
        WHERE m.user_id = $1
        LIMIT 1
    """
    row = await pool.fetchrow(sql, user_id)
    if not row:
        return None
    return {"user1_id": row["user1_id"], "user2_id": row["user2_id"], "created_at": row["created_at"]}


async def db_get_pending_proposal(pool, partner_id: int) -> Optional[Dict[str, Any]]:
    sql = """
        SELECT proposer_id, partner_id, created_at
        FROM wedding_proposals
        WHERE partner_id = $1 AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT 1
    """
    row = await pool.fetchrow(sql, partner_id)
    if not row:
        return None
    return {"proposer_id": row["proposer_id"], "partner_id": row["partner_id"], "created_at": row["created_at"]}


async def db_create_proposal(pool, proposer_id: int, partner_id: int, created_at: datetime) -> None:
    sql = """
        INSERT INTO wedding_proposals (proposer_id, partner_id, created_at, status)
        VALUES ($1, $2, $3, 'pending')
    """
    await pool.execute(sql, proposer_id, partner_id, created_at)


async def db_accept_proposal(pool, partner_id: int, accepted_at: datetime) -> Dict[str, Any]:
    select_proposal = """
        SELECT id, proposer_id, partner_id
        FROM wedding_proposals
        WHERE partner_id = $1 AND status = 'pending'
        ORDER BY created_at DESC
        LIMIT 1
        FOR UPDATE
    """

    check_in_marriage = "SELECT 1 FROM wedding_members WHERE user_id = $1 LIMIT 1"

    insert_wedding = """
        INSERT INTO weddings (user1_id, user2_id, created_at)
        VALUES ($1, $2, $3)
        RETURNING id, user1_id, user2_id, created_at
    """

    insert_member = """
        INSERT INTO wedding_members (wedding_id, user_id)
        VALUES ($1, $2)
    """

    update_proposal = "UPDATE wedding_proposals SET status='accepted' WHERE id=$1"

    async with pool.acquire() as conn:
        async with conn.transaction():
            proposal = await conn.fetchrow(select_proposal, partner_id)
            if not proposal:
                raise ValueError("No pending proposal")

            proposal_id = proposal["id"]
            proposer_id = int(proposal["proposer_id"])
            partner_id_db = int(proposal["partner_id"])

            if await conn.fetchrow(check_in_marriage, proposer_id):
                raise ValueError("Proposer already married")
            if await conn.fetchrow(check_in_marriage, partner_id_db):
                raise ValueError("Partner already married")

            u1 = min(proposer_id, partner_id_db)
            u2 = max(proposer_id, partner_id_db)

            wedding = await conn.fetchrow(insert_wedding, u1, u2, accepted_at)

            await conn.execute(insert_member, wedding["id"], u1)
            await conn.execute(insert_member, wedding["id"], u2)

            await conn.execute(update_proposal, proposal_id)

            return {
                "user1_id": int(wedding["user1_id"]),
                "user2_id": int(wedding["user2_id"]),
                "created_at": wedding["created_at"],
            }

async def db_divorce_by_user(pool, user_id: int):
    get_wedding = """
        SELECT w.id AS wedding_id, w.user1_id, w.user2_id, w.created_at
        FROM wedding_members m
        JOIN weddings w ON w.id = m.wedding_id
        WHERE m.user_id = $1
        LIMIT 1
        FOR UPDATE
    """

    delete_wedding = "DELETE FROM weddings WHERE id = $1"

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(get_wedding, user_id)
            if not row:
                return None

            wedding_id = int(row["wedding_id"])
            u1 = int(row["user1_id"])
            u2 = int(row["user2_id"])
            created_at = row["created_at"]

            partner_id = u2 if user_id == u1 else u1

            await conn.execute(delete_wedding, wedding_id)

            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            days = max(0, (_utcnow() - created_at.astimezone(timezone.utc)).days)

            return {"partner_id": partner_id, "days": days}