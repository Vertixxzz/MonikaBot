from datetime import datetime

async def recalculate_cards_for_chat(conn, chat_id: int) -> int:
    now = datetime.utcnow()

    await conn.execute(
        """
        UPDATE user_cards
        SET state = 'LEGACY'
        WHERE chat_id = $1
          AND user_id IN (
              SELECT user_id
              FROM user_stats
              WHERE chat_id = $1
                AND ispresent = FALSE
          )
        """,
        chat_id,
    )

    rows = await conn.fetch(
        """
        SELECT user_id, messages_total
        FROM user_stats
        WHERE chat_id = $1
          AND ispresent = TRUE
          AND messages_total > 0
        ORDER BY messages_total DESC
        """,
        chat_id,
    )

    if not rows:
        return 0

    total = len(rows)

    for index, row in enumerate(rows):
        rank = index + 1
        percentile = rank / total
        rarity = determine_rarity(percentile)

        await conn.execute(
            """
            INSERT INTO user_cards (
                chat_id,
                user_id,
                rarity,
                percentile,
                messages_total,
                calculated_at,
                state
            )
            VALUES ($1, $2, $3, $4, $5, $6, 'ACTIVE')
            ON CONFLICT (chat_id, user_id) DO UPDATE SET
                rarity = EXCLUDED.rarity,
                percentile = EXCLUDED.percentile,
                messages_total = EXCLUDED.messages_total,
                calculated_at = EXCLUDED.calculated_at,
                state = 'ACTIVE'
            """,
            chat_id,
            row["user_id"],
            rarity,
            percentile,
            row["messages_total"],
            now,
        )

    return total

from datetime import datetime

RARITY_RULES = (
    (0.05, "LEGENDARY"),
    (0.20, "EPIC"),
    (0.50, "RARE"),
)

def determine_rarity(percentile: float) -> str:
    for limit, rarity in RARITY_RULES:
        if percentile <= limit:
            return rarity
    return "COMMON"
