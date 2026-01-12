from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")

def today_msk_date() -> date:
    return datetime.now(MSK).date()

async def try_consume_game(pool, user_id: int, day_msk: date, limit: int) -> tuple[bool, int]:
    sql = """
    INSERT INTO user_daily_hangman (user_id, day_msk, games_used)
    VALUES ($1, $2, 1)
    ON CONFLICT (user_id, day_msk) DO UPDATE
      SET games_used = user_daily_hangman.games_used + 1,
          updated_at = now()
    WHERE user_daily_hangman.games_used < $3
    RETURNING games_used;
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, user_id, day_msk, limit)

    if row is None:
        return False, 0

    used = int(row["games_used"])
    return True, max(0, limit - used)


async def get_remaining_games(pool, user_id: int, day_msk: date, limit: int) -> int:
    sql = "SELECT games_used FROM user_daily_hangman WHERE user_id=$1 AND day_msk=$2;"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, user_id, day_msk)

    used = int(row["games_used"]) if row else 0
    return max(0, limit - used)
