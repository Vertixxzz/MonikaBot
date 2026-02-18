from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.types import Message

from common.db.weddings import (
    db_get_marriage_by_user,
    db_get_pending_proposal,
    db_create_proposal,
    db_accept_proposal,
)

router = Router()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _days_since(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (_utcnow() - dt.astimezone(timezone.utc)).days)


def _fmt_user(u) -> str:
    if getattr(u, "username", None):
        return f"@{u.username}"
    return (getattr(u, "full_name", None) or "пользователь").strip()


@router.message(F.text.func(lambda t: t and t.strip().lower() == "брак"))
async def marriage_propose(message: Message, pool):
    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.answer("Сделай `брак` ответом на сообщение человека, которому хочешь сделать предложение.")
        return

    proposer = message.from_user
    partner = message.reply_to_message.from_user

    if not proposer or not partner:
        await message.answer("Не смогла понять участников брака :(")
        return
    if partner.is_bot:
        await message.answer("С ботами нельзя!")
        return
    if proposer.id == partner.id:
        await message.answer("Сам(а) с собой? Это.. грустно")
        return

    if await db_get_marriage_by_user(pool, proposer.id):
        await message.answer("Ты уже в браке. Изменщик!")
        return
    if await db_get_marriage_by_user(pool, partner.id):
        await message.answer("Этот человек уже в браке.")
        return

    if await db_get_pending_proposal(pool, partner.id):
        await message.answer("У этого человека уже есть активное предложение. Пусть сначала разберётся с ним.")
        return

    created_at = _utcnow()
    await db_create_proposal(pool, proposer.id, partner.id, created_at)

    await message.answer(
        "💍 *Предложение руки и сердца!*\n\n"
        f"{_fmt_user(proposer)} делает предложение {_fmt_user(partner)}.\n"
        "Чтобы принять, напиши: `брак принять`",
        parse_mode="Markdown",
    )


@router.message(F.text.func(lambda t: t and t.strip().lower() == "брак принять"))
async def marriage_accept(message: Message, pool):
    user = message.from_user
    if not user:
        return

    if await db_get_marriage_by_user(pool, user.id):
        await message.answer("Ты уже в браке! Подлый изменщик")
        return

    pending = await db_get_pending_proposal(pool, user.id)
    if not pending:
        await message.answer("У тебя нет активных предложений брака.")
        return

    accepted_at = _utcnow()
    try:
        marriage = await db_accept_proposal(pool, user.id, accepted_at)
    except ValueError:
        await message.answer("Это предложение уже недоступно (возможно, его приняли/отозвали).")
        return
    except Exception:
        await message.answer("Не смогла оформить брак из-за ошибки. Попробуй ещё раз чуть позже.")
        return

    await message.answer(
        "*Брак заключён!>w<*\n\n"
        f"ID пары: `{marriage['user1_id']}` + `{marriage['user2_id']}`\n"
        f"Дата: `{marriage['created_at']}`\n"
        "Живите долго и счастливо :*",
        parse_mode="Markdown",
    )


@router.message(F.text.func(lambda t: t and t.strip().lower() == "брак инфо"))
async def marriage_info(message: Message, pool):
    user = message.from_user
    if not user:
        return

    marriage = await db_get_marriage_by_user(pool, user.id)
    if not marriage:
        await message.answer("Ты не в браке. Пока что^-^")
        return

    created_at = marriage["created_at"]
    days = _days_since(created_at)
    partner_id = marriage["user2_id"] if user.id == marriage["user1_id"] else marriage["user1_id"]

    await message.answer(
        "*Информация о браке*\n\n"
        f"Ты женат(а) с: `{partner_id}`\n"
        f"Дата свадьбы: `{created_at}`\n"
        f"Прошло дней: *{days}*",
        parse_mode="Markdown",
    )
