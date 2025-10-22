import asyncpg

db_pool = None

async def connect_db():
    global db_pool
    db_pool = await asyncpg.create_pool(
        user='postgres',
        password='123',
        database='postgres',
        host='127.0.0.1',
        port=5432
    )
    return db_pool
