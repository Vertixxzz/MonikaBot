from datetime import date

async def try_consume_payout(pool, user_id: int, day_msk: date, limit: int) -> tuple[bool, int]:
    sql = """
    INSERT INTO user_daily_game_payouts (user_id, day_msk, payouts)
    VALUES ($1, $2, 1)
    ON CONFLICT (user_id, day_msk) DO UPDATE
      SET payouts = user_daily_game_payouts.payouts + 1,
          updated_at = now()
    WHERE user_daily_game_payouts.payouts < $3
    RETURNING payouts;
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql, user_id, day_msk, limit)

    if row is None:
        return False, 0

    payouts = int(row["payouts"])
    return True, max(0, limit - payouts)
