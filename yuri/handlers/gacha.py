from __future__ import annotations

import logging
import html

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from common.db.gacha import roll_once, ROLL_COST_DEFAULT
from common.db.utilities import get_usernames_by_ids
from common.db.gacha_menus import upsert_gacha_menu, get_gacha_menu_owner  # <--
from yuri.handlers.card import get_user_avatar_file_id, get_legacy_avatar

logger = logging.getLogger(__name__)
router = Router()

GACHA_ROLL_CB = "yuri_gacha_roll"

GACHA_MENU_TTL_MINUTES = 20


def gacha_roll_keyboard() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Крутить", callback_data=GACHA_ROLL_CB)
    return kb.as_markup()


def _esc(s: str) -> str:
    return html.escape(s, quote=True)


def _format_user_link(user_id: int, username: str | None) -> str:
    if not username:
        label = "Юзер"
    else:
        label = username.strip()
        if label.startswith("@"):
            label = label[1:]
        label = label.strip() or "Юзер"

    return f'<a href="tg://user?id={user_id}">{_esc(label)}</a>'


def _build_roll_top_html(dropped_user_id: int, dropped_username: str | None, copies: int) -> str:
    user_link = _format_user_link(dropped_user_id, dropped_username)
    return "\n".join(
        [
            f"Пользователь: {user_link}",
            f"Копий этой карточки: <b>x{int(copies)}</b>",
        ]
    )


def _build_pity_html(since_epic: int, since_legendary: int) -> str:
    since_epic = int(since_epic)
    since_legendary = int(since_legendary)
    epic_left = max(0, 30 - since_epic)
    lega_left = max(0, 70 - since_legendary)

    return "\n".join(
        [
            f"Гарант EPIC: <code>{since_epic}/30</code> (осталось ~<code>{epic_left}</code>)",
            f"Гарант LEGENDARY: <code>{since_legendary}/70</code> (осталось ~<code>{lega_left}</code>)",
        ]
    )


async def send_card_by_user_id(
    message: types.Message,
    pool,
    chat_id: int,
    target_user_id: int,
    header: str,
    top_html: str = "",
    pity_html: str = "",
    reply_markup: InlineKeyboardMarkup | None = None,
) -> types.Message | None:
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
        return None

    rarity = str(row["rarity"])
    state = str(row["state"])
    percentile = float(row["percentile"]) * 100
    messages_total = int(row["messages_total"])
    calculated_at = row["calculated_at"]

    if state == "LEGACY":
        rarity_text = f"{rarity}, LEGACY"
        footer = (
            "\n\n<i>Эта карточка больше не создаётся.</i>\n"
            "<i>Но я всё ещё её помню.</i>"
        )
    else:
        rarity_text = rarity
        footer = ""

    caption = (
        f"<b>{_esc(header)}</b>\n"
        + (f"{top_html}\n\n" if top_html else "\n")
        + f"Редкость: <b>{_esc(rarity_text)}</b>\n"
        + f"Сообщений учтено: <code>{messages_total}</code>\n"
        + f"Активнее, чем ~<code>{100 - percentile:.1f}%</code> участников этого чата\n\n"
        + (f"{pity_html}\n\n" if pity_html else "")
        + f"<i>Последнее обновление: {calculated_at:%d.%m.%Y}</i>"
        + f"{footer}"
    )

    avatar_file_id = await get_user_avatar_file_id(message.bot, target_user_id)

    try:
        if avatar_file_id and state == "LEGACY":
            photo = await get_legacy_avatar(message.bot, avatar_file_id)
            sent = await message.answer_photo(
                photo=photo,
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            return sent

        if avatar_file_id:
            sent = await message.answer_photo(
                photo=avatar_file_id,
                caption=caption,
                parse_mode="HTML",
                reply_markup=reply_markup,
            )
            return sent

        sent = await message.answer(
            caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return sent

    except Exception:
        logger.exception("Failed to send gacha card")
        sent = await message.answer(
            caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
        )
        return sent


@router.message(F.text.func(lambda t: t and t.lower().strip() == "юри крутка"))
async def yuri_gacha_menu(message: types.Message, pool):
    sent = await message.answer(
        f"Карточка стоит <code>{ROLL_COST_DEFAULT}</code>.\n"
        "Хочешь покрутить?..",
        parse_mode="HTML",
        reply_markup=gacha_roll_keyboard(),
    )

    await upsert_gacha_menu(
        pool=pool,
        chat_id=sent.chat.id,
        message_id=sent.message_id,
        owner_id=message.from_user.id,
    )

@router.callback_query(F.data == GACHA_ROLL_CB)
async def yuri_gacha_roll_callback(query: types.CallbackQuery, pool):
    if not query.message:
        await query.answer("Нет сообщения у callback", show_alert=True)
        return

    message = query.message
    chat_id = message.chat.id
    msg_id = message.message_id

    owner_id = await get_gacha_menu_owner(
        pool=pool,
        chat_id=chat_id,
        message_id=msg_id,
        ttl_minutes=GACHA_MENU_TTL_MINUTES,
    )

    if owner_id is None:
        await query.answer("Прошлое меню устарело - я отправлю новое", show_alert=True)
        sent = await message.answer(
            f"Карточка стоит <code>{ROLL_COST_DEFAULT}</code>.\nХочешь покрутить?..",
            parse_mode="HTML",
            reply_markup=gacha_roll_keyboard(),
        )
        await upsert_gacha_menu(pool, sent.chat.id, sent.message_id, query.from_user.id)
        return

    if query.from_user.id != int(owner_id):
        await query.answer("Эта кнопка не для тебя!", show_alert=True)
        return

    await query.answer()

    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    user = query.from_user
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
                bal = await conn.fetchval(
                    "SELECT balance FROM wallets WHERE user_id = $1",
                    user_id,
                )
            bal = int(bal or 0)

            await message.answer(
                "Не хватает докидолларов\n"
                f"Нужно: <code>{ROLL_COST_DEFAULT}</code>\n"
                f"У тебя: <code>{bal}</code>",
                parse_mode="HTML",
                reply_markup=gacha_roll_keyboard(),
            )
            return

        await message.answer(
            "Пул карточек пустой",
            reply_markup=gacha_roll_keyboard(),
        )
        return

    dropped_user_id = int(result.dropped_user_id)

    names = await get_usernames_by_ids(pool, [dropped_user_id])
    dropped_username = names.get(dropped_user_id)

    top_html = _build_roll_top_html(
        dropped_user_id=dropped_user_id,
        dropped_username=dropped_username,
        copies=int(getattr(result, "copies", 0) or 0),
    )

    pity_html = _build_pity_html(
        since_epic=int(getattr(result, "since_epic", 0) or 0),
        since_legendary=int(getattr(result, "since_legendary", 0) or 0),
    )

    sent_card = await send_card_by_user_id(
        message=message,
        pool=pool,
        chat_id=chat_id,
        target_user_id=dropped_user_id,
        header="Твоя крутка",
        top_html=top_html,
        pity_html=pity_html,
        reply_markup=gacha_roll_keyboard(),
    )

    if sent_card:
        await upsert_gacha_menu(
            pool=pool,
            chat_id=sent_card.chat.id,
            message_id=sent_card.message_id,
            owner_id=query.from_user.id,
        )



