async def save_advice(pool, user_id: int, username: str, chat_id: int, content: str):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO advices (user_id, username, chat_id, content)
            VALUES ($1, $2, $3, $4)
            """,
            user_id, username, chat_id, content
        )

async def get_random_advice(pool):
    async with pool.acquire() as conn:
        result = await conn.fetchrow("SELECT content FROM advices ORDER BY random() LIMIT 1;")
        return result["content"] if result else None