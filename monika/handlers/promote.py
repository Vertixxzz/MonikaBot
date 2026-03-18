# /monika/handlers/admin_rank.py
from __future__ import annotations
import re
import asyncio
from aiogram import Router, F
from aiogram.types import Message
import html

from common.db.admin import (
    get_bot_level,
    upsert_bot_level,
    remove_bot_admin,
    list_bot_admins,
)
from common.db.utilities import (
    get_user_id_by_username,
    get_usernames_by_ids,
)

router = Router()

LEVEL_TITLE: dict[int, str] = {
    1: "Младший модератор",
    2: "Старший модератор",
    3: "Младший админ",
    4: "Старший админ",
    5: "Создатель",
}

_BAD_NUMBER_TOKEN = re.compile(r"^[+-]?\d+([\-–]\d+)+$")  # 1-5, 1–5
_SIGNED_INT = re.compile(r"^[+-]?\d+$")                  # -1, +2, 3


def level_title(level: int) -> str:
    return LEVEL_TITLE.get(level, f"Уровень {level}")

def format_user(user_id, username):
    if username:
        name = f"@{username}"
    else:
        name = str(user_id)

    return f'<a href="tg://user?id={user_id}">{html.escape(name)}</a>'

def parse_first_int(text: str, default: int = 1) -> int | None:
    parts = (text or "").split()

    for p in parts:
        if _BAD_NUMBER_TOKEN.match(p):
            return None

    for p in parts:
        if _SIGNED_INT.match(p):
            return int(p)

    return default

def clamp_level(level: int) -> int:
    return max(1, min(5, level))


async def resolve_target_user_id(pool, message: Message) -> int | None:
    # reply -> username -> None
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id

    for p in (message.text or "").split():
        if p.startswith("@") and len(p) > 1:
            return await get_user_id_by_username(pool, p)

    return None


async def get_tg_mark(message: Message, user_id: int) -> str:
    try:
        member = await message.bot.get_chat_member(message.chat.id, user_id)
        if member.status in ("administrator", "creator"):
            return "Телеграм-админ"
        return "Не Телеграм-админ"
    except Exception:
        return "Не вижу статус"


@router.message(F.text.lower().in_({"кто админ", "кто модер"}))
async def who_admins_handler(message: Message, pool) -> None:
    chat_id = message.chat.id

    rows = await list_bot_admins(pool, chat_id, min_level=1)
    if not rows:
        await message.reply("Пока в вашем чате нету админов, которых вы попросили меня записать")
        return

    user_ids = [user_id for user_id, _ in rows]
    usernames = await get_usernames_by_ids(pool, user_ids)

    marks = await asyncio.gather(
        *(get_tg_mark(message, user_id) for user_id, _ in rows),
        return_exceptions=False,
    )

    lines: list[str] = []
    for (user_id, level), mark in zip(rows, marks):
        lines.append(
            f"• {format_user(user_id, usernames.get(user_id))} - {level_title(level)} - {mark}"
        )

    await message.reply("Назначенные звания:\n" + "\n".join(lines), parse_mode="HTML")


@router.message(F.text.lower().startswith("повысить"))
async def promote_handler(message: Message, pool) -> None:
    chat_id = message.chat.id
    actor_id = message.from_user.id

    delta = parse_first_int(message.text, default=1)
    if delta is None or delta <= 0 or delta > 5:
        await message.reply("Укажи число рангов 1–5: например 'повысить 2'.")
        return

    target_id = await resolve_target_user_id(pool, message)
    if not target_id:
        await message.reply("Укажи пользователя реплаем или используй его юзернейм")
        return
    if target_id == actor_id:
        await message.reply("Ага! Захотел, еще чего?")
        return

    actor_level = await get_bot_level(pool, chat_id, actor_id)
    if not actor_level:
        await message.reply("У тебя нету никакого ранга чтоб выполнить это действие!")
        return

    target_level = await get_bot_level(pool, chat_id, target_id) or 0

    if target_level >= actor_level:
        await message.reply("Ты не можешь поменять чей-то ранг, если его ранг выше или раен твоему!")
        return

    new_level = clamp_level(target_level + delta)
    if new_level > actor_level:
        new_level = actor_level

    if new_level == target_level:
        await message.reply("Ничего не изменилось (уже на максимуме прав).")
        return

    await upsert_bot_level(pool, chat_id, target_id, new_level, assigned_by=actor_id)

    usernames = await get_usernames_by_ids(pool, [target_id])
    mark = await get_tg_mark(message, target_id)
    old_t = level_title(target_level) if target_level else "нет звания"

    await message.reply(
        f"Готово: {format_user(target_id, usernames.get(target_id))}\n"
        f"{old_t} → {level_title(new_level)}\n"
        f"{mark}",
        parse_mode="HTML",
    )


@router.message(F.text.lower().startswith("понизить"))
async def demote_handler(message: Message, pool) -> None:
    chat_id = message.chat.id
    actor_id = message.from_user.id

    delta = parse_first_int(message.text, default=1)
    if delta is None or delta <= 0 or delta > 5:
        await message.reply("Укажи число рангов 1–5: например 'повысить 2'.")
        return

    target_id = await resolve_target_user_id(pool, message)
    if not target_id:
        await message.reply("Укажи пользователя реплаем или используй его юзернейм")
        return
    if target_id == actor_id:
        await message.reply("Используй 'увольняюсь' или 'ухожу в отставку' если хочешь снять с себя звание")
        return

    actor_level = await get_bot_level(pool, chat_id, actor_id)
    if not actor_level:
        await message.reply("У тебя нету никакого ранга чтоб выполнить это действие!")
        return

    target_level = await get_bot_level(pool, chat_id, target_id)
    if not target_level:
        await message.reply("Как мне известно - этот юзер уже без звания")
        return

    if target_level >= actor_level:
        await message.reply("Ты не можешь поменять чей-то ранг, если его ранг выше или раен твоему!")
        return

    new_level = target_level - delta

    usernames = await get_usernames_by_ids(pool, [target_id])
    mark = await get_tg_mark(message, target_id)

    if new_level < 1:
        await remove_bot_admin(pool, chat_id, target_id)
        await message.reply(
            f"Готово: {format_user(target_id, usernames.get(target_id))}\n"
            f"{level_title(target_level)} → снято звание\n"
            f"{mark}",
            parse_mode="HTML",
        )
        return

    new_level = clamp_level(new_level)
    if new_level == target_level:
        await message.reply("Ничего не изменилось.")
        return

    await upsert_bot_level(pool, chat_id, target_id, new_level, assigned_by=actor_id)
    await message.reply(
        f"Готово: {format_user(target_id, usernames.get(target_id))}\n"
        f"{level_title(target_level)} → {level_title(new_level)}\n"
        f"{mark}",
        parse_mode="HTML",
    )


@router.message(F.text.lower().startswith("разжаловать"))
async def strip_rank_handler(message: Message, pool) -> None:
    chat_id = message.chat.id
    actor_id = message.from_user.id

    target_id = await resolve_target_user_id(pool, message)
    if not target_id:
        await message.reply("Укажи пользователя реплаем или используй его юзернейм")
        return
    if target_id == actor_id:
        await message.reply("Используй 'увольняюсь' или 'ухожу в отставку' если хочешь снять с себя звание")
        return

    actor_level = await get_bot_level(pool, chat_id, actor_id)
    if not actor_level:
        await message.reply("У тебя нету никакого ранга чтоб выполнить это действие!")
        return

    target_level = await get_bot_level(pool, chat_id, target_id)
    if not target_level:
        await message.reply("Как мне известно - этот юзер уже без звания")
        return

    if target_level >= actor_level:
        await message.reply("Ты не можешь поменять чей-то ранг, если его ранг выше или раен твоему!")
        return

    await remove_bot_admin(pool, chat_id, target_id)

    usernames = await get_usernames_by_ids(pool, [target_id])
    mark = await get_tg_mark(message, target_id)

    await message.reply(
        f"Готово: {format_user(target_id, usernames.get(target_id))}\n"
        f"{level_title(target_level)} -> снято звание\n"
        f"{mark}",
        parse_mode="HTML",
    )

@router.message(F.text.lower().in_({"увольняюсь", "ухожу в отставку"}))
async def resign_handler(message: Message, pool) -> None:
    chat_id = message.chat.id
    user_id = message.from_user.id

    level = await get_bot_level(pool, chat_id, user_id)
    if not level:
        await message.reply("Но.. у тебя нету звания чтоб покинуть его")
        return

    await remove_bot_admin(pool, chat_id, user_id)
    await message.reply(f"Принято. Твое звание «{level_title(level)}» снято.")

@router.message(F.text.lower() == "восстановить права")
async def restore_rights_handler(message: Message, pool) -> None:
    chat_id = message.chat.id
    user_id = message.from_user.id

    try:
        member = await message.bot.get_chat_member(chat_id, user_id)
    except Exception:
        await message.reply("Телеграм считает что тебя не существует, прикинь")
        return

    if member.status != "creator":
        await message.reply("Команда доступна только создателю чата")
        return

    current = await get_bot_level(pool, chat_id, user_id)
    if current == 5:
        await message.reply("У тебя уже есть права создателя")
        return

    await upsert_bot_level(pool, chat_id, user_id, level=5, assigned_by=user_id)
    old = f" (было: «{level_title(current)}»)" if current else ""
    await message.reply(f"Готово. Права восстановлены: теперь ты «Создатель».{old}")