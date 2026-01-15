# /yuri/handlers/gacha.py

import logging
from aiogram import Router, types, F

from common.bd.gacha import roll_once, ROLL_COST_DEFAULT
from common.db.utilities import get_usernames_by_ids
from yuri.handlers.card import get_user_avatar_file_id, get_legacy_avatar

logger = logging.getLogger(__name__)
router = Router()


def _format_user_display(username: str | None, user_id: int) -> str:
    if not username:
        return f"`id {user_id}`"
    u = username.strip()
    if u.startswith("@"):
        return f"{u}"
    if " " not in u and not u.startswith("#"):
        return f"@{u}"
    return f"*{u}*"


def _build_roll_extra_text(dropped_user_id: int, dropped_username: str | None, copies: int, since_epic: int, since_legendary: int) -> str:
    epic_left = max(0, 30 - int(since_epic))
    lega_left = max(0, 70 - int(since_legendary))

    user_text = _format_user_display(dropped_username, dropped_user_id)

    lines = [
        f"Пользователь: {user_text}",
        f"Копий этой карточки: *x{copies}*",
        "",
        f"Гарант EPIC: `{since_epic}/30` (осталось ~`{epic_left}`)",
        f"Гарант LEGENDARY: `{since_legendary}/70` (осталось ~`{lega_left}`)",
    ]
    return "\n".join(lines)


async def send_card_by_user_id(
    message: types.Message,
    pool,
    chat_id: int,
    target_user_id: int,
    header: str,
    extra_text: str = "",
):
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
        f"*{header}*\n"
        + (f"{extra_text}\n\n" if extra_text else "\n")
        + f"Редкость: *{rarity_text}*\n"
        + f"Сообщений учтено: `{messages_total}`\n"
        + f"Активнее, чем ~`{percentile:.1f}%` участников этого чата\n\n"
        + f"_Последнее обновление: {calculated_at:%d.%m.%Y}_"
        + f"{footer}"
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
                f"Не хватает докидолларов\n"
                f"Нужно: `{ROLL_COST_DEFAULT}`\n"
                f"У тебя: `{bal}`",
                parse_mode="Markdown",
            )
            return

        await message.answer("Пул карточек пустой")
        return

    dropped_user_id = int(result.dropped_user_id)

    names = await get_usernames_by_ids(pool, [dropped_user_id])
    dropped_username = names.get(dropped_user_id)

    extra_text = _build_roll_extra_text(
        dropped_user_id=dropped_user_id,
        dropped_username=dropped_username,
        copies=int(getattr(result, "copies", 0) or 0),
        since_epic=int(getattr(result, "since_epic", 0) or 0),
        since_legendary=int(getattr(result, "since_legendary", 0) or 0),
    )

    await send_card_by_user_id(
        message=message,
        pool=pool,
        chat_id=chat_id,
        target_user_id=dropped_user_id,
        header="Твоя крутка",
        extra_text=extra_text,
    )
