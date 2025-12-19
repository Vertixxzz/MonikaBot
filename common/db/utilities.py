async def get_user_id_by_username(pool, username: str) -> int | None:
    q = username.lstrip("@")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT user_id
            FROM user_stats
            WHERE username = $1
               OR username ILIKE '%' || $1 || '%'
            ORDER BY last_message_date DESC
            LIMIT 1
            """,
            q,
        )
        return row["user_id"] if row else None
