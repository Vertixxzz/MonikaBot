# /common/bd/gacha.py

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Literal, Optional

from asyncpg import Pool


ROLL_COST_DEFAULT = 350

PITY_EPIC = 30
PITY_LEGENDARY = 70

LEGACY_OVERRIDE_DENOM = 20  # 1/20

RARITY_PROBS = [
    ("LEGENDARY", 0.02),
    ("EPIC", 0.15),
    ("RARE", 0.33),
    ("COMMON", 0.50),
]

RARITY_DOWNGRADE = {
    "LEGENDARY": "EPIC",
    "EPIC": "RARE",
    "RARE": "COMMON",
    "COMMON": None,
}


FailReason = Literal["NOT_ENOUGH_BALANCE", "POOL_EMPTY"]


@dataclass(frozen=True)
class RollResult:
    ok: bool
    dropped_user_id: Optional[int] = None
    reason: Optional[FailReason] = None
    spent: int = 0


def _roll_rarity_with_pity(since_epic: int, since_legendary: int) -> str:
    if since_legendary >= PITY_LEGENDARY:
        return "LEGENDARY"
    if since_epic >= PITY_EPIC:
        return "EPIC"

    r = random.random()
    acc = 0.0
    for rarity, p in RARITY_PROBS:
        acc += p
        if r < acc:
            return rarity
    return "COMMON"


async def _ensure_wallet_row_locked(conn, user_id: int, username: str) -> int:
    await conn.execute(
        """
        INSERT INTO wallets (user_id, username, balance, updated_at)
        VALUES ($1, $2, 0, now())
        ON CONFLICT (user_id) DO NOTHING
        """,
        user_id, username,
    )
    # лочим
    bal = await conn.fetchval(
        """
        SELECT balance
        FROM wallets
        WHERE user_id = $1
        FOR UPDATE
        """,
        user_id,
    )
    return int(bal or 0)


async def _ensure_gacha_state_locked(conn, chat_id: int, user_id: int) -> tuple[int, int]:
    await conn.execute(
        """
        INSERT INTO gacha_state (chat_id, user_id, since_epic, since_legendary, updated_at)
        VALUES ($1, $2, 0, 0, now())
        ON CONFLICT (chat_id, user_id) DO NOTHING
        """,
        chat_id, user_id,
    )

    row = await conn.fetchrow(
        """
        SELECT since_epic, since_legendary
        FROM gacha_state
        WHERE chat_id = $1 AND user_id = $2
        FOR UPDATE
        """,
        chat_id, user_id,
    )
    return int(row["since_epic"]), int(row["since_legendary"])


async def _pick_card_user_id(conn, chat_id: int, starting_rarity: str) -> Optional[int]:
    rarity = starting_rarity

    while rarity is not None:
        counts = await conn.fetchrow(
            """
            SELECT
              COUNT(*) FILTER (WHERE state = 'LEGACY') AS legacy_cnt,
              COUNT(*) FILTER (WHERE state = 'ACTIVE') AS active_cnt
            FROM user_cards
            WHERE chat_id = $1
              AND rarity = $2
            """,
            chat_id, rarity,
        )

        legacy_cnt = int(counts["legacy_cnt"] or 0)
        active_cnt = int(counts["active_cnt"] or 0)

        if legacy_cnt + active_cnt == 0:
            rarity = RARITY_DOWNGRADE[rarity]
            continue

        if legacy_cnt > 0:
            want_legacy = (random.randrange(LEGACY_OVERRIDE_DENOM) == 0)
            state = "LEGACY" if want_legacy else "ACTIVE"
        else:
            state = "ACTIVE"

        if state == "ACTIVE" and active_cnt == 0:
            state = "LEGACY"
        if state == "LEGACY" and legacy_cnt == 0:
            state = "ACTIVE"

        row = await conn.fetchrow(
            """
            SELECT user_id
            FROM user_cards
            WHERE chat_id = $1
              AND rarity = $2
              AND state = $3
            ORDER BY random()
            LIMIT 1
            """,
            chat_id, rarity, state,
        )

        if row:
            return int(row["user_id"])

        rarity = RARITY_DOWNGRADE[rarity]

    return None


async def _add_to_inventory(conn, chat_id: int, owner_id: int, card_user_id: int) -> None:
    await conn.execute(
        """
        INSERT INTO gacha_inventory (chat_id, owner_id, card_user_id, copies, last_drop_at)
        VALUES ($1, $2, $3, 1, now())
        ON CONFLICT (chat_id, owner_id, card_user_id)
        DO UPDATE SET
          copies = gacha_inventory.copies + 1,
          last_drop_at = now()
        """,
        chat_id, owner_id, card_user_id,
    )


async def _apply_pity_update(conn, chat_id: int, user_id: int, dropped_rarity: str) -> None:
    if dropped_rarity == "EPIC":
        await conn.execute(
            """
            UPDATE gacha_state
            SET since_epic = 0,
                since_legendary = since_legendary + 1,
                updated_at = now()
            WHERE chat_id = $1 AND user_id = $2
            """,
            chat_id, user_id,
        )
    elif dropped_rarity == "LEGENDARY":
        await conn.execute(
            """
            UPDATE gacha_state
            SET since_legendary = 0,
                since_epic = since_epic + 1,
                updated_at = now()
            WHERE chat_id = $1 AND user_id = $2
            """,
            chat_id, user_id,
        )
    else:
        await conn.execute(
            """
            UPDATE gacha_state
            SET since_epic = since_epic + 1,
                since_legendary = since_legendary + 1,
                updated_at = now()
            WHERE chat_id = $1 AND user_id = $2
            """,
            chat_id, user_id,
        )


async def roll_once(pool: Pool, chat_id: int, user_id: int, username: str, cost: int = ROLL_COST_DEFAULT) -> RollResult:
    async with pool.acquire() as conn:
        async with conn.transaction():
            balance = await _ensure_wallet_row_locked(conn, user_id, username)
            if balance < cost:
                return RollResult(ok=False, reason="NOT_ENOUGH_BALANCE", spent=0)

            since_epic, since_legendary = await _ensure_gacha_state_locked(conn, chat_id, user_id)

            await conn.execute(
                """
                UPDATE wallets
                SET balance = balance - $2,
                    username = $3,
                    updated_at = now()
                WHERE user_id = $1
                """,
                user_id, cost, username,
            )

            target_rarity = _roll_rarity_with_pity(since_epic, since_legendary)
            dropped_user_id = await _pick_card_user_id(conn, chat_id, target_rarity)

            if dropped_user_id is None:
                await conn.execute(
                    "UPDATE wallets SET balance = balance + $2, updated_at = now() WHERE user_id = $1",
                    user_id, cost,
                )
                return RollResult(ok=False, reason="POOL_EMPTY", spent=0)

            dropped_rarity = await conn.fetchval(
                "SELECT rarity FROM user_cards WHERE chat_id = $1 AND user_id = $2",
                chat_id, dropped_user_id,
            )
            dropped_rarity = str(dropped_rarity)

            await _add_to_inventory(conn, chat_id, user_id, dropped_user_id)
            await _apply_pity_update(conn, chat_id, user_id, dropped_rarity)

            return RollResult(ok=True, dropped_user_id=dropped_user_id, spent=cost)
