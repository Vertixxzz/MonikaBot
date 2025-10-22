async def get_balance(pool, user_id: int, chat_id: int) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT balance FROM wallets WHERE user_id = $1 AND chat_id = $2",
            user_id, chat_id
        )
        return row["balance"] if row else 0


async def add_balance(pool, user_id: int, chat_id: int, username: str, amount: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO wallets (user_id, chat_id, username, balance)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id, chat_id)
            DO UPDATE SET
                balance   = wallets.balance + EXCLUDED.balance,
                username  = EXCLUDED.username,
                updated_at = now()
        """, user_id, chat_id, username, amount)


async def set_balance(pool, user_id: int, chat_id: int, amount: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO wallets (user_id, chat_id, balance)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, chat_id)
            DO UPDATE SET
                balance   = EXCLUDED.balance,
                updated_at = now()
        """, user_id, chat_id, amount)

async def add_wallet(pool, user_id: int, chat_id: int, username: str):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO wallets (user_id, chat_id, username, balance, updated_at)
            VALUES ($1, $2, $3, 0, now())
            ON CONFLICT (user_id, chat_id) DO NOTHING
        """, user_id, chat_id, username)

async def transfer_money(pool, sender_id: int, receiver_id: int, chat_id: int, username_rec: str, amount: int):
    async with pool.acquire() as conn:
        async with conn.transaction():
            sender = await conn.fetchrow(
                "SELECT balance FROM wallets WHERE user_id = $1 AND chat_id = $2",
                sender_id, chat_id
            )
            receiver = await conn.fetchrow(
                "SELECT balance FROM wallets WHERE user_id = $1 AND chat_id = $2",
                receiver_id, chat_id
            )

            if not sender:
                raise ValueError("У отправителя нет кошелька")

            if sender["balance"] < amount:
                raise ValueError("Недостаточно средств")

            # 🪄 Используем готовую функцию
            if not receiver:
                await add_wallet(pool, receiver_id, chat_id, username_rec)
                receiver = {"balance": 0}

            await conn.execute(
                "UPDATE wallets SET balance = balance - $1, updated_at = now() WHERE user_id = $2 AND chat_id = $3",
                amount, sender_id, chat_id
            )

            await conn.execute(
                "UPDATE wallets SET balance = balance + $1, username = $2, updated_at = now() WHERE user_id = $3 AND chat_id = $4",
                amount, username_rec, receiver_id, chat_id
            )
