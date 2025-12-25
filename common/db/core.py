from cfg import DATABASE_URL
import asyncpg

db_pool: asyncpg.Pool | None = None

async def connect_db() -> asyncpg.Pool:
    global db_pool
    dsn = DATABASE_URL
    db_pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=10)
    return db_pool

async def close_db() -> None:
    global db_pool
    if db_pool is not None:
        await db_pool.close()
        db_pool = None