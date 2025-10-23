from asyncpg import Pool


async def get_balance(pool: Pool, user_id: int) -> int:
    async with pool.acquire() as conn:
        balance = await conn.fetchval(
            "SELECT balance FROM wallets WHERE user_id = $1",
            user_id
        )
        return balance or 0


async def add_balance(pool: Pool, user_id: int, username: str, amount: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO wallets (user_id, username, balance, updated_at)
            VALUES ($1, $2, $3, now())
            ON CONFLICT (user_id)
            DO UPDATE SET
                balance = wallets.balance + EXCLUDED.balance,
                username = EXCLUDED.username,
                updated_at = now()
        """, user_id, username, amount)


async def set_balance(pool: Pool, user_id: int, amount: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO wallets (user_id, balance, updated_at)
            VALUES ($1, $2, now())
            ON CONFLICT (user_id)
            DO UPDATE SET
                balance = EXCLUDED.balance,
                updated_at = now()
        """, user_id, amount)


async def add_wallet(pool: Pool, user_id: int, username: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO wallets (user_id, username, balance, updated_at)
            VALUES ($1, $2, 0, now() - interval '2 hours')
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, username)


async def add_wallet_conn(conn, user_id: int, username: str):
    await conn.execute("""
        INSERT INTO wallets (user_id, username, balance, updated_at)
        VALUES ($1, $2, 0, now())
        ON CONFLICT (user_id) DO NOTHING
    """, user_id, username)


async def transfer_money(pool: Pool, sender_id: int, receiver_id: int, username_rec: str, amount: int):
    async with pool.acquire() as conn:
        async with conn.transaction():
            sender_balance = await conn.fetchval(
                "SELECT balance FROM wallets WHERE user_id = $1",
                sender_id
            )

            if sender_balance is None:
                raise ValueError("У отправителя нет кошелька")

            if sender_balance < amount:
                raise ValueError("Недостаточно средств")

            receiver_exists = await conn.fetchval(
                "SELECT 1 FROM wallets WHERE user_id = $1",
                receiver_id
            )

            if not receiver_exists:
                await add_wallet_conn(conn, receiver_id, username_rec)

            await conn.execute(
                "UPDATE wallets SET balance = balance - $1, updated_at = now() WHERE user_id = $2",
                amount, sender_id
            )

            await conn.execute(
                "UPDATE wallets SET balance = balance + $1, username = $2, updated_at = now() WHERE user_id = $3",
                amount, username_rec, receiver_id
            )
