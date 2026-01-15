from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable

from asyncpg import Pool

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PresenceSyncStats:
    total: int
    set_true: int
    set_false: int
    skipped_errors: int


PRESENT_STATUSES = {"member", "administrator", "creator", "restricted"}
ABSENT_STATUSES = {"left", "kicked"}


async def sync_presence_for_chat(bot, pool: Pool, chat_id: int, *, per_request_delay: float = 0.05) -> PresenceSyncStats:
    async with pool.acquire() as conn:
        user_rows = await conn.fetch(
            """
            SELECT user_id
            FROM user_stats
            WHERE chat_id = $1
            """,
            chat_id,
        )

    user_ids: list[int] = [int(r["user_id"]) for r in user_rows]
    total = len(user_ids)

    updates: list[tuple[int, bool]] = []
    set_true = 0
    set_false = 0
    skipped = 0

    for uid in user_ids:
        if per_request_delay:
            await asyncio.sleep(per_request_delay)

        try:
            member = await bot.get_chat_member(chat_id, uid)
            status = getattr(member, "status", None)

            if status in PRESENT_STATUSES:
                updates.append((uid, True))
                set_true += 1
            elif status in ABSENT_STATUSES:
                updates.append((uid, False))
                set_false += 1
            else:
                skipped += 1
                logger.warning("Unknown chat member status=%r for uid=%s chat_id=%s", status, uid, chat_id)


        except Exception as e:

            text = str(e).lower()

            if "member not found" in text or "user not found" in text:
                updates.append((uid, False))
                set_false += 1
                logger.info("Presence: uid=%s chat_id=%s is absent (%s)", uid, chat_id, e)

            else:
                skipped += 1
                logger.warning("Presence check failed for uid=%s chat_id=%s: %r", uid, chat_id, e)

    if updates:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.executemany(
                    """
                    UPDATE user_stats
                    SET ispresent = $2
                    WHERE chat_id = $1
                      AND user_id = $3
                    """,
                    [(chat_id, ispresent, uid) for uid, ispresent in updates],
                )

    return PresenceSyncStats(
        total=total,
        set_true=set_true,
        set_false=set_false,
        skipped_errors=skipped,
    )
