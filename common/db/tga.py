from __future__ import annotations

from asyncpg import Pool

QUESTIONS_COUNT = 20

# Колонки reply1..reply20 — whitelist, чтобы имя колонки в SQL никогда не шло от пользователя
REPLY_COLUMNS = tuple(f"reply{i}" for i in range(1, QUESTIONS_COUNT + 1))

_table_ready = False


async def ensure_tga_table(pool: Pool) -> None:
    """Создаёт таблицу при первом обращении (один раз за жизнь процесса)."""
    global _table_ready
    if _table_ready:
        return

    replies_sql = ",\n".join(f"    {col} TEXT" for col in REPLY_COLUMNS)
    sql = f"""
    CREATE TABLE IF NOT EXISTS tga_nominations (
        user_id      BIGINT PRIMARY KEY,
        username     TEXT,
        full_name    TEXT,
    {replies_sql},
        current_q    SMALLINT NOT NULL DEFAULT 1,
        started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMPTZ
    )
    """
    async with pool.acquire() as conn:
        await conn.execute(sql)
    _table_ready = True


async def tga_get(pool: Pool, user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM tga_nominations WHERE user_id = $1", user_id
        )


async def tga_start(pool: Pool, user_id: int, username: str | None, full_name: str | None) -> int:
    """Создаёт запись (если её нет) и возвращает номер вопроса, с которого продолжать."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO tga_nominations (user_id, username, full_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name,
                updated_at = NOW()
            RETURNING current_q
            """,
            user_id, username, full_name,
        )
        return int(row["current_q"])


async def tga_reset(pool: Pool, user_id: int) -> None:
    """Стирает ответы и начинает опрос с первого вопроса."""
    nulls = ", ".join(f"{col} = NULL" for col in REPLY_COLUMNS)
    async with pool.acquire() as conn:
        await conn.execute(
            f"""
            UPDATE tga_nominations
            SET {nulls}, current_q = 1, completed_at = NULL,
                started_at = NOW(), updated_at = NOW()
            WHERE user_id = $1
            """,
            user_id,
        )


async def tga_save_reply(pool: Pool, user_id: int, q_num: int, text: str | None) -> None:
    """Сохраняет ответ на вопрос q_num (None = пропуск) и двигает прогресс."""
    if not 1 <= q_num <= QUESTIONS_COUNT:
        raise ValueError(f"bad question number: {q_num}")
    col = REPLY_COLUMNS[q_num - 1]
    is_last = q_num == QUESTIONS_COUNT

    async with pool.acquire() as conn:
        await conn.execute(
            f"""
            UPDATE tga_nominations
            SET {col} = $2,
                current_q = $3,
                updated_at = NOW(),
                completed_at = CASE WHEN $4 THEN NOW() ELSE completed_at END
            WHERE user_id = $1
            """,
            user_id, text, q_num + 1, is_last,
        )
