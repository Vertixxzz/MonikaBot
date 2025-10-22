from cfg import DB_SCHEMA

TABLE = f'{DB_SCHEMA}.beer_stats' if DB_SCHEMA else 'public.beer_stats'

async def drink_beer(pool, user_id: int, chat_id: int, beer_amount: float):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO beer_stats (user_id, chat_id, amount)
            VALUES ($1, $2, $3)
            ON CONFLICT ON CONSTRAINT beer_stats_user_chat_unique
            DO UPDATE SET
                amount = beer_stats.amount + EXCLUDED.amount,
                updated_at = now()
            """,
            user_id,
            chat_id,
            beer_amount,
        )

async def get_beer(pool, user_id: int, chat_id: int) -> float:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT amount FROM beer_stats WHERE user_id = $1 AND chat_id = $2",
            user_id, chat_id
        )
        return float(row["amount"]) if row and row["amount"] is not None else 0.0