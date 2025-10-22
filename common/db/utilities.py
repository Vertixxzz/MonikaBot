async def get_user_id_by_username(pool, username: str, chat_id: int):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT user_id FROM wallets WHERE username = $1 AND chat_id = $2
        """, username, chat_id)
        return row["user_id"] if row else None