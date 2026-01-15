import logging
from aiogram import Router, types, F

from common.db.gacha import roll_once, ROLL_COST_DEFAULT
from yuri.handlers.card import get_user_avatar_file_id, get_legacy_avatar

logger = logging.getLogger(__name__)
router = Router()


async def send_card_by_user_id(message: types.Message, pool, chat_id: int, target_user_id: int, header: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                rarity,
                percentile,
                messages_total,
                calculated_at,
                state
            FROM user_cards
            WHERE chat_id = $1
              AND user_id = $2
            """,
            chat_id,
            target_user_id,
        )

    if not row:
        await message.answer("Карточка не найдена")
        return

    rarity = row["rarity"]
    state = row["state"]
    percentile = row["percentile"] * 100
    messages_total = row["messages_total"]
    calculated_at = row["calculated_at"]

    if state == "LEGACY":
        rarity_text = f"{rarity}, LEGACY ️"
        footer = (
            "\n\n_Эта карточка больше не создаётся._\n"
            "_Но я всё ещё её помню._"
        )
    else:
        rarity_text = rarity
        footer = ""

    caption = (
        f"*{header}*\n\n"
        f"Редкость: *{rarity_text}*\n"
        f"Сообщений учтено: `{messages_total}`\n"
        f"Активнее, чем ~`{percentile:.1f}%` участников этого чата\n\n"
        f"_Последнее обновление: {calculated_at:%d.%m.%Y}_"
        f"{footer}"
    )

    avatar_file_id = await get_user_avatar_file_id(message.bot, target_user_id)

    try:
        if avatar_file_id and state == "LEGACY":
            photo = await get_legacy_avatar(message.bot, avatar_file_id)
            await message.answer_photo(photo=photo, caption=caption, parse_mode="Markdown")
        elif avatar_file_id:
            await message.answer_photo(photo=avatar_file_id, caption=caption, parse_mode="Markdown")
        else:
            await message.answer(caption, parse_mode="Markdown")
    except Exception:
        logger.exception("Failed to send gacha card")
        await message.answer(caption, parse_mode="Markdown")


@router.message(F.text.func(lambda t: t and t.lower().strip() == "юри крутка"))
async def yuri_roll(message: types.Message, pool):
    chat_id = message.chat.id
    user = message.from_user
    user_id = user.id
    username = user.username or user.full_name or "unknown"

    result = await roll_once(
        pool=pool,
        chat_id=chat_id,
        user_id=user_id,
        username=username,
        cost=ROLL_COST_DEFAULT,
    )

    if not result.ok:
        if result.reason == "NOT_ENOUGH_BALANCE":
            async with pool.acquire() as conn:
                bal = await conn.fetchval("SELECT balance FROM wallets WHERE user_id = $1", user_id)
            bal = int(bal or 0)

            await message.answer(
                f"Тебе не хватает докидолларов\n"
                f"Нужно: `{ROLL_COST_DEFAULT}`\n"
                f"У тебя: `{bal}`",
                parse_mode="Markdown",
            )
            return

        await message.answer("Пул карточек пустой")
        return

    await send_card_by_user_id(
        message=message,
        pool=pool,
        chat_id=chat_id,
        target_user_id=int(result.dropped_user_id),
        header="Твоя крутка",
    )
