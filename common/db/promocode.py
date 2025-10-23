from asyncpg import Pool


# Получаем информацию о промокоде
async def get_promo(pool: Pool, code: str):
    async with pool.acquire() as conn:
        return await conn.fetchrow("""
            SELECT * FROM promo_codes
            WHERE LOWER(code) = LOWER($1)
              AND active = TRUE
              AND (expires_at IS NULL OR expires_at > NOW())
        """, code)


# Проверяем, использовал ли пользователь этот промокод
async def check_promo_usage(pool: Pool, user_id: int, promo_id: int) -> bool:
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT 1 FROM promo_usages
            WHERE user_id = $1 AND promo_id = $2
        """, user_id, promo_id)
        return row is not None


# Записываем факт использования промокода
async def mark_promo_used(pool: Pool, user_id: int, promo_id: int):
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO promo_usages (user_id, promo_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
        """, user_id, promo_id)


# Активируем промокод (с наградой)
async def activate_promo(pool: Pool, user_id: int, code: str):
    async with pool.acquire() as conn:
        async with conn.transaction():
            promo = await conn.fetchrow("""
                SELECT * FROM promo_codes
                WHERE LOWER(code) = LOWER($1)
                  AND active = TRUE
                  AND (expires_at IS NULL OR expires_at > NOW())
            """, code)

            if not promo:
                raise ValueError("invalid_code")

            promo_id = promo["id"]
            reward = promo["reward_amount"]

            # Проверяем, не активировал ли юзер этот промо ранее
            already = await conn.fetchrow("""
                SELECT 1 FROM promo_usages
                WHERE user_id = $1 AND promo_id = $2
            """, user_id, promo_id)

            if already:
                raise ValueError("already_used")

            # Проверяем лимит активаций
            if promo["max_uses"] is not None:
                count = await conn.fetchval("""
                    SELECT COUNT(*) FROM promo_usages WHERE promo_id = $1
                """, promo_id)
                if count >= promo["max_uses"]:
                    raise ValueError("limit_reached")

            # Отмечаем использование промо
            await conn.execute("""
                INSERT INTO promo_usages (user_id, promo_id)
                VALUES ($1, $2)
            """, user_id, promo_id)

            # Обновляем баланс пользователя
            await conn.execute("""
                UPDATE wallets
                SET balance = balance + $1, updated_at = NOW()
                WHERE user_id = $2
            """, reward, user_id)

            return reward

