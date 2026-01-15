from __future__ import annotations

import math
import logging

from aiogram import Router, types, F
from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from common.db.utilities import get_usernames_by_ids
from yuri.handlers.gacha import send_card_by_user_id  # поправь путь, если у тебя иначе

logger = logging.getLogger(__name__)
router = Router()

PAGE_SIZE = 10

CB_PAGE = "yuri:coll:page"
CB_OPEN = "yuri:coll:open"
CB_BACK = "yuri:coll:back"
CB_NOOP = "yuri:coll:noop"


# -------------------- helpers --------------------
def _cut(s: str, n: int = 20) -> str:
    s = (s or "").strip()
    if len(s) <= n:
        return s
    return s[: n - 1] + "…"


def _rarity_emoji(rarity: str) -> str:
    r = (rarity or "").upper()
    if r == "LEGENDARY":
        return "🟨"
    if r == "EPIC":
        return "🟣"
    if r == "RARE":
        return "🟦"
    return "⬜"


async def _count_collection(pool, chat_id: int, owner_id: int) -> int:
    async with pool.acquire() as conn:
        n = await conn.fetchval(
            """
            SELECT COUNT(*)
            FROM gacha_inventory
            WHERE chat_id=$1 AND owner_id=$2
            """,
            chat_id,
            owner_id,
        )
    return int(n or 0)


async def _fetch_collection_page(pool, chat_id: int, owner_id: int, page: int):
    offset = (page - 1) * PAGE_SIZE
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT
              gi.card_user_id,
              gi.copies,
              gi.last_drop_at,
              uc.rarity,
              uc.state
            FROM gacha_inventory gi
            JOIN user_cards uc
              ON uc.chat_id = gi.chat_id AND uc.user_id = gi.card_user_id
            WHERE gi.chat_id = $1
              AND gi.owner_id = $2
            ORDER BY
              CASE uc.rarity
                WHEN 'LEGENDARY' THEN 4
                WHEN 'EPIC' THEN 3
                WHEN 'RARE' THEN 2
                ELSE 1
              END DESC,
              gi.copies DESC,
              gi.last_drop_at DESC,
              gi.card_user_id ASC
            LIMIT $3 OFFSET $4
            """,
            chat_id,
            owner_id,
            PAGE_SIZE,
            offset,
        )
    return rows


def _build_header(page: int, pages: int) -> str:
    return f"<b>Коллекция Юри</b>\nСтраница <b>{page}</b>/<b>{pages}</b>"


def _kb_collection(
    owner_id: int,
    page: int,
    pages: int,
    rows: list,
    names: dict[int, str | None],
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()

    for r in rows:
        uid = int(r["card_user_id"])
        copies = int(r["copies"] or 0)
        rarity = str(r["rarity"])
        state = str(r["state"])

        name = names.get(uid)
        label = _cut(name or str(uid), 20)

        emoji = _rarity_emoji(rarity)
        legacy = " 🕯" if state == "LEGACY" else ""
        text = f"{emoji} {label} ×{copies}{legacy}"

        kb.button(text=text, callback_data=f"{CB_OPEN}:{owner_id}:{page}:{uid}")

    kb.adjust(1)

    nav = InlineKeyboardBuilder()
    if page > 1:
        nav.button(text="⬅️", callback_data=f"{CB_PAGE}:{owner_id}:{page-1}")
    else:
        nav.button(text="⬅️", callback_data=CB_NOOP)

    nav.button(text=f"{page}/{pages}", callback_data=CB_NOOP)

    if page < pages:
        nav.button(text="➡️", callback_data=f"{CB_PAGE}:{owner_id}:{page+1}")
    else:
        nav.button(text="➡️", callback_data=CB_NOOP)

    nav.adjust(3)
    for row in nav.export():
        kb.row(*row)

    return kb.as_markup()


def _kb_back(owner_id: int, page: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад к коллекции", callback_data=f"{CB_BACK}:{owner_id}:{page}")
    return kb.as_markup()


# -------------------- noop --------------------
@router.callback_query(F.data == CB_NOOP)
async def _noop(q: types.CallbackQuery):
    await q.answer()


# -------------------- command --------------------
@router.message(F.text.func(lambda t: t and t.lower().strip() == "юри коллекция"))
async def yuri_collection(message: types.Message, pool):
    chat_id = message.chat.id
    owner_id = message.from_user.id
    page = 1

    total = await _count_collection(pool, chat_id, owner_id)
    if total <= 0:
        await message.answer("<b>Коллекция Юри</b>\n\n<i>Пусто.</i>", parse_mode="HTML")
        return

    pages = max(1, math.ceil(total / PAGE_SIZE))
    rows = await _fetch_collection_page(pool, chat_id, owner_id, page)

    ids = [int(r["card_user_id"]) for r in rows]
    names = await get_usernames_by_ids(pool, ids)

    await message.answer(
        _build_header(page, pages),
        parse_mode="HTML",
        reply_markup=_kb_collection(owner_id, page, pages, list(rows), names),
    )


# -------------------- pagination --------------------
@router.callback_query(F.data.startswith(f"{CB_PAGE}:"))
async def yuri_collection_page(q: types.CallbackQuery, pool):
    await q.answer()
    if not q.message:
        return

    parts = (q.data or "").split(":")
    if len(parts) < 5:
        return

    owner_id = int(parts[-2])
    page = int(parts[-1])

    if q.from_user.id != owner_id:
        await q.answer("Это меню не для тебя", show_alert=True)
        return

    chat_id = q.message.chat.id
    total = await _count_collection(pool, chat_id, owner_id)
    if total <= 0:
        await q.message.edit_text("<b>Коллекция Юри</b>\n\n<i>Пусто.</i>", parse_mode="HTML")
        return

    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, pages))

    rows = await _fetch_collection_page(pool, chat_id, owner_id, page)
    ids = [int(r["card_user_id"]) for r in rows]
    names = await get_usernames_by_ids(pool, ids)

    await q.message.edit_text(
        _build_header(page, pages),
        parse_mode="HTML",
        reply_markup=_kb_collection(owner_id, page, pages, list(rows), names),
    )


# -------------------- open card --------------------
@router.callback_query(F.data.startswith(f"{CB_OPEN}:"))
async def yuri_collection_open(q: types.CallbackQuery, pool):
    await q.answer()
    if not q.message:
        return

    parts = (q.data or "").split(":")
    if len(parts) < 6:
        return

    owner_id = int(parts[-3])
    page = int(parts[-2])
    card_user_id = int(parts[-1])

    if q.from_user.id != owner_id:
        await q.answer("Это меню не для тебя", show_alert=True)
        return

    await send_card_by_user_id(
        message=q.message,
        pool=pool,
        chat_id=q.message.chat.id,
        target_user_id=card_user_id,
        header="Карточка из коллекции",
        reply_markup=_kb_back(owner_id, page),
    )


# -------------------- back to page --------------------
@router.callback_query(F.data.startswith(f"{CB_BACK}:"))
async def yuri_collection_back(q: types.CallbackQuery, pool):
    await q.answer()
    if not q.message:
        return

    parts = (q.data or "").split(":")
    if len(parts) < 5:
        return

    owner_id = int(parts[-2])
    page = int(parts[-1])

    if q.from_user.id != owner_id:
        await q.answer("Это меню не для тебя", show_alert=True)
        return

    chat_id = q.message.chat.id
    total = await _count_collection(pool, chat_id, owner_id)
    if total <= 0:
        await q.message.edit_text("<b>Коллекция Юри</b>\n\n<i>Пусто.</i>", parse_mode="HTML")
        return

    pages = max(1, math.ceil(total / PAGE_SIZE))
    page = max(1, min(page, pages))

    rows = await _fetch_collection_page(pool, chat_id, owner_id, page)
    ids = [int(r["card_user_id"]) for r in rows]
    names = await get_usernames_by_ids(pool, ids)

    await q.message.edit_text(
        _build_header(page, pages),
        parse_mode="HTML",
        reply_markup=_kb_collection(owner_id, page, pages, list(rows), names),
    )
