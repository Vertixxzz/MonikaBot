from __future__ import annotations

async def get_user_id_by_username(pool, username: str) -> int | None:
    q = username.lstrip("@")

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT user_id
            FROM user_stats
            WHERE username = $1
               OR username ILIKE $1 || '%'
               OR username ILIKE '%' || $1 || '%'
            ORDER BY
              (username = $1) DESC,
              (username ILIKE $1 || '%') DESC,
              last_message_date DESC
            LIMIT 1
            """,
            q,
        )
        return int(row["user_id"]) if row else None


async def get_usernames_by_ids(pool, user_ids: list[int]) -> dict[int, str]:
    """
    user_id -> username (самый свежий по last_message_date).
    Если по user_id нет записи/username, ключа не будет.
    """
    if not user_ids:
        return {}

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (user_id)
                user_id,
                username
            FROM user_stats
            WHERE user_id = ANY($1)
              AND username IS NOT NULL
              AND username <> ''
            ORDER BY user_id, last_message_date DESC
            """,
            user_ids,
        )

    return {int(r["user_id"]): str(r["username"]) for r in rows}