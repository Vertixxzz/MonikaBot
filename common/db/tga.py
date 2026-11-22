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


async def tga_all(pool: Pool) -> list:
    """Все анкеты: сначала завершённые (по времени), потом незавершённые."""
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT * FROM tga_nominations
            ORDER BY completed_at IS NULL, completed_at, started_at
            """
        )


async def tga_find(pool: Pool, query: str):
    """Ищет анкету по user_id или username (с @ или без)."""
    q = query.strip().lstrip("@")
    async with pool.acquire() as conn:
        if q.lstrip("-").isdigit():
            return await conn.fetchrow(
                "SELECT * FROM tga_nominations WHERE user_id = $1", int(q)
            )
        return await conn.fetchrow(
            "SELECT * FROM tga_nominations WHERE LOWER(username) = LOWER($1)", q
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


# =====================================================================
#  Этап 2: голосование по шорт-листу
# =====================================================================
#
# Таблицы создаются сами при первом обращении (ensure_vote_tables):
#   tga_settings — переключатели этапов, переживают перезапуск контейнера:
#                  stage1_open = '1'/'0' — сбор номинантов (по умолчанию открыт)
#                  vote_open   = '1'/'0' — голосование (по умолчанию ЗАКРЫТО)
#   tga_voters   — кто голосует: ник, когда начал, когда впервые ответил на все номинации
#   tga_votes    — сами голоса: одна строка на (человек, номинация);
#                  choice = номер финалиста в tga_finalists (с 0) или NULL = «пропустил»

STAGE1_OPEN = "stage1_open"
VOTE_OPEN = "vote_open"
_SETTING_DEFAULTS = {STAGE1_OPEN: "1", VOTE_OPEN: "0"}

_vote_tables_ready = False


async def ensure_vote_tables(pool: Pool) -> None:
    """Создаёт таблицы этапа 2 (один раз за жизнь процесса)."""
    global _vote_tables_ready
    if _vote_tables_ready:
        return
    async with pool.acquire() as conn:
        # Без аргументов asyncpg шлёт строку одним простым запросом,
        # поэтому несколько CREATE TABLE через «;» работают.
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tga_settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tga_voters (
                user_id      BIGINT PRIMARY KEY,
                username     TEXT,
                full_name    TEXT,
                started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ
            );
            CREATE TABLE IF NOT EXISTS tga_votes (
                user_id    BIGINT   NOT NULL REFERENCES tga_voters(user_id) ON DELETE CASCADE,
                nomination SMALLINT NOT NULL,
                choice     SMALLINT,
                voted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (user_id, nomination)
            );
            """
        )
    _vote_tables_ready = True


# ---------- переключатели этапов ----------

async def tga_setting_get(pool: Pool, key: str) -> bool:
    await ensure_vote_tables(pool)
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT value FROM tga_settings WHERE key = $1", key)
    return (val if val is not None else _SETTING_DEFAULTS.get(key, "0")) == "1"


async def tga_setting_set(pool: Pool, key: str, enabled: bool) -> None:
    await ensure_vote_tables(pool)
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO tga_settings (key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            key, "1" if enabled else "0",
        )


# ---------- голосующие и голоса ----------

async def vote_start(pool: Pool, user_id: int, username: str | None, full_name: str | None):
    """Регистрирует голосующего (или обновляет ник) и возвращает его строку tga_voters."""
    await ensure_vote_tables(pool)
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO tga_voters (user_id, username, full_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id) DO UPDATE SET
                username = EXCLUDED.username,
                full_name = EXCLUDED.full_name,
                updated_at = NOW()
            RETURNING *
            """,
            user_id, username, full_name,
        )


async def vote_get_voter(pool: Pool, user_id: int):
    await ensure_vote_tables(pool)
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM tga_voters WHERE user_id = $1", user_id)


async def vote_find_voter(pool: Pool, query: str):
    """Ищет голосующего по user_id или username (с @ или без)."""
    await ensure_vote_tables(pool)
    q = query.strip().lstrip("@")
    async with pool.acquire() as conn:
        if q.lstrip("-").isdigit():
            return await conn.fetchrow("SELECT * FROM tga_voters WHERE user_id = $1", int(q))
        return await conn.fetchrow(
            "SELECT * FROM tga_voters WHERE LOWER(username) = LOWER($1)", q
        )


async def vote_get_choices(pool: Pool, user_id: int) -> dict[int, int | None]:
    """{номинация: номер финалиста или None (пропуск)} — только где человек уже нажал кнопку."""
    await ensure_vote_tables(pool)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT nomination, choice FROM tga_votes WHERE user_id = $1", user_id
        )
    return {int(r["nomination"]): r["choice"] for r in rows}


async def vote_save(pool: Pool, user_id: int, nomination: int, choice: int | None, total: int):
    """Записывает голос (повторное нажатие перезаписывает) и возвращает строку tga_voters.

    completed_at ставится один раз — в момент, когда у человека впервые появился
    ответ (голос или пропуск) во всех total номинациях. Дальнейшие правки его не трогают.
    """
    await ensure_vote_tables(pool)
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO tga_votes (user_id, nomination, choice)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, nomination) DO UPDATE SET
                    choice = EXCLUDED.choice,
                    voted_at = NOW()
                """,
                user_id, nomination, choice,
            )
            # Подзапрос видит строку, вставленную выше: это та же транзакция.
            return await conn.fetchrow(
                """
                UPDATE tga_voters
                SET updated_at = NOW(),
                    completed_at = CASE
                        WHEN completed_at IS NULL AND (
                            SELECT COUNT(*) FROM tga_votes
                            WHERE user_id = $1 AND nomination BETWEEN 1 AND $2
                        ) >= $2
                        THEN NOW()
                        ELSE completed_at
                    END
                WHERE user_id = $1
                RETURNING *
                """,
                user_id, total,
            )


async def vote_all_voters(pool: Pool) -> list:
    """Все голосующие: сначала завершившие (по времени), потом остальные."""
    await ensure_vote_tables(pool)
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM tga_voters ORDER BY completed_at IS NULL, completed_at, started_at"
        )


async def vote_all_votes(pool: Pool) -> list:
    await ensure_vote_tables(pool)
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT user_id, nomination, choice, voted_at FROM tga_votes"
        )
