import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")

from aiogram import Router, F
from aiogram.types import Message, ChatPermissions
from aiogram.exceptions import TelegramBadRequest

from common.db.warnings import (
    add_warning,
    get_warnings,
    clear_warnings,
    remove_one_warning,
    get_warning_events,
)
from common.db.utilities import get_user_id_by_username

router = Router()

ADMIN_STATUSES = ("administrator", "creator")


# -------------------- helpers --------------------

async def require_admin(message: Message) -> bool:
    chat_id = message.chat.id
    sender_id = message.from_user.id
    sender_member = await message.bot.get_chat_member(chat_id, sender_id)
    if sender_member.status not in ADMIN_STATUSES:
        await message.answer("Нужны права администратора.")
        return False
    return True


def who_label(display: str | None) -> str:
    if not display:
        return "пользователь"
    if display.startswith("@"):
        return display
    # если это ник без @
    if " " not in display:
        return f"@{display}"
    return display


def tg_human_error(e: TelegramBadRequest) -> str:
    msg = (getattr(e, "message", "") or "").lower()

    if "user is an administrator" in msg:
        return "Нельзя применить действие: пользователь администратор/создатель."
    if "not enough rights" in msg or "rights" in msg:
        return "Недостаточно прав у бота для этого действия."
    if "can't restrict self" in msg or "can’t restrict self" in msg:
        return "Нельзя применить действие к самому боту."
    if "user not found" in msg:
        return "Пользователь не найден."
    if "can't remove chat owner" in msg:
        return "Нельзя применить действие к владельцу чата"
    if "PARTICIPANT_ID_INVALID" in msg:
        return "Ты указал неправильного пользователя/ничего не указал"
    return f"Ошибка Telegram: {getattr(e, 'message', str(e))}"


async def deny_if_self(message: Message, target_id: int, action_word: str) -> bool:
    if target_id == message.bot.id:
        await message.answer(f"Эй! {action_word} меня - ужасный выбор!")
        return True
    return False


async def resolve_target_user(message: Message, pool, username_pos: int = 1) -> tuple[int | None, str | None]:
    chat_id = message.chat.id
    text = (message.text or "").strip()

    if message.reply_to_message:
        u = message.reply_to_message.from_user
        display = u.username or u.full_name
        return u.id, display

    parts = text.split()
    if len(parts) <= username_pos:
        return None, None

    username = parts[username_pos].lstrip("@")
    if not username:
        return None, None

    user_id = await get_user_id_by_username(pool, username)
    return user_id, username


def parse_duration(text: str) -> timedelta | None:
    text = (text or "").strip().lower()
    if not text:
        raise ValueError("empty duration")

    text = (
        text.replace("мин.", "минут")
            .replace("час.", "час")
            .replace("дн.", "день")
    )

    pattern = re.compile(
        r"(\d+)\s*(?:"
        r"(минут(?:а|ы)?|м|m)"
        r"|"
        r"(час(?:а|ов)?|ч|h)"
        r"|"
        r"(день|дня|дней|д|d)"
        r")\b",
        re.IGNORECASE
    )

    matches = pattern.findall(text)
    if not matches:
        raise ValueError("Я не смогла понять какова длительность")

    total = timedelta(0)

    for num_str, min_unit, hour_unit, day_unit in matches:
        n = int(num_str)
        if min_unit:
            total += timedelta(minutes=n)
        elif hour_unit:
            total += timedelta(hours=n)
        elif day_unit:
            total += timedelta(days=n)

    if total <= timedelta(0):
        raise ValueError("Длительность должна быть больше нуля")

    return total


def extract_reason_from_second_line(message: Message) -> str | None:
    lines = (message.text or "").splitlines()
    if len(lines) >= 2 and lines[1].strip():
        return lines[1].strip()
    return None


# --------- SMART ARG PARSING (duration + inline tail) ---------

def get_args_after_target(message: Message, username_pos: int = 1) -> list[str]:
    first_line = (message.text or "").splitlines()[0].strip()
    parts = first_line.split()

    if message.reply_to_message:
        start = 1  # после команды
    else:
        start = username_pos + 1  # после @username

    return parts[start:] if len(parts) > start else []


def split_duration_and_tail(args: list[str]) -> tuple[timedelta | None, str, str]:
    if not args:
        return None, "", ""

    # Ищем самое длинное удачное совпадение с начала:
    # "1ч 15м", "15 минут", "7д", ...
    best_delta = None
    best_len = 0

    for i in range(1, len(args) + 1):
        candidate = " ".join(args[:i])
        try:
            d = parse_duration(candidate)
        except ValueError:
            continue
        else:
            best_delta = d
            best_len = i

    if best_len == 0:
        # Ничего не похоже на время => времени нет, а всё args — хвост (возможная причина)
        return None, "", " ".join(args).strip()

    duration_text = " ".join(args[:best_len]).strip()
    tail_text = " ".join(args[best_len:]).strip()
    return best_delta, duration_text, tail_text


def extract_reason(message: Message, inline_tail: str | None = None) -> str | None:
    second = extract_reason_from_second_line(message)
    if second:
        return second
    if inline_tail:
        t = inline_tail.strip()
        return t if t else None
    return None


# -------------------- WARN --------------------

@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "варн")
async def warn_user_handler(message: Message, pool):
    if not await require_admin(message):
        return

    chat_id = message.chat.id
    lines = (message.text or "").splitlines()

    if message.reply_to_message:
        u = message.reply_to_message.from_user
        target_id = u.id
        username = u.username or u.full_name
    else:
        parts = lines[0].split()
        if len(parts) < 2:
            await message.answer(
                "Укажи пользователя реплаем или так: `варн @username`.\n"
                "Причину можно второй строкой."
            )
            return

        username = parts[1].lstrip("@")
        target_id = await get_user_id_by_username(pool, username)
        if not target_id:
            await message.answer("Не удалось найти пользователя.")
            return

    reason = extract_reason_from_second_line(message) or "нарушение правил"

    await add_warning(pool, target_id, username, chat_id, reason)
    data = await get_warnings(pool, target_id, chat_id)
    count = data["count"]

    if count >= 3:
        try:
            if await deny_if_self(message, target_id, "забанить"):
                return
            await message.bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
            await clear_warnings(pool, target_id, chat_id)
            await message.answer(
                f"{who_label(username)} получил 3 предупреждения и был забанен.\n"
                f"Причина последнего нарушения: {reason}"
            )
        except TelegramBadRequest as e:
            await message.answer(tg_human_error(e))
            await clear_warnings(pool, target_id, chat_id)
    else:
        await message.answer(
            f"{who_label(username)} получил предупреждение.\n"
            f"Причина: {reason}\n"
            f"Всего предупреждений: {count}/3"
        )


@router.message(F.text.lower().startswith("снять варн"))
async def warn_user_snyat(message: Message, pool):
    if not await require_admin(message):
        return

    chat_id = message.chat.id

    if message.reply_to_message:
        u = message.reply_to_message.from_user
        user_id = u.id
        username = u.username or u.full_name
    else:
        parts = (message.text or "").split()
        # "снять варн @user"
        if len(parts) < 3:
            await message.answer("Укажи пользователя: `снять варн @username` (или реплаем).")
            return
        username = parts[2].lstrip("@")
        user_id = await get_user_id_by_username(pool, username)
        if not user_id:
            await message.answer("Не удалось найти пользователя.")
            return

    data = await get_warnings(pool, user_id, chat_id)
    if not data or data["count"] == 0:
        await message.answer("У данного пользователя нет варнов.")
        return

    await remove_one_warning(pool, user_id, username, chat_id)
    await message.answer(f"С пользователя {who_label(username)} был снят 1 варн.")


@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "варны")
async def showwarn_handler(message: Message, pool):
    chat_id = message.chat.id

    if message.reply_to_message:
        u = message.reply_to_message.from_user
        user_id = u.id
        username = u.username or u.full_name
    else:
        parts = (message.text or "").split()
        if len(parts) < 2:
            await message.answer("Укажи пользователя: `варны @username` (или реплаем).")
            return
        username = parts[1].lstrip("@")
        user_id = await get_user_id_by_username(pool, username)
        if not user_id:
            await message.answer("Не удалось найти пользователя.")
            return

    data = await get_warnings(pool, user_id, chat_id)
    if not data or data["count"] == 0:
        await message.answer("У данного пользователя нет варнов.")
        return

    events = await get_warning_events(pool, user_id, chat_id, limit=10)

    lines = []
    for i, e in enumerate(events, start=1):
        reason = (e["reason"] or "Нарушение правил").strip()
        dt = e["warned_at"].astimezone(MSK)
        dt_str = dt.strftime("%d.%m.%Y %H:%M")
        lines.append(f"{i}) `{dt_str} МСК` - {reason}")

    await message.answer(
        f"У пользователя {who_label(username)} {data['count']} варнов.\n"
        f"Последние {len(lines)}:\n" + "\n".join(lines)
    )


# -------------------- MUTE / UNMUTE --------------------

@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "мут")
async def mute_handler(message: Message, pool):
    if not await require_admin(message):
        return

    chat_id = message.chat.id
    user_id, display = await resolve_target_user(message, pool, username_pos=1)

    if not user_id:
        await message.answer("Укажи пользователя реплаем или так: `мут @username 15 минут` (время опционально).")
        return

    if await deny_if_self(message, user_id, "замутить"):
        return

    args = get_args_after_target(message, username_pos=1)
    delta, duration_text, tail = split_duration_and_tail(args)

    until_date = None
    if delta is not None:
        until_date = datetime.now(timezone.utc) + delta

    try:
        await message.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
    except TelegramBadRequest as e:
        await message.answer(tg_human_error(e))
        return

    who = who_label(display)
    if delta is None:
        await message.answer(f"{who} замучен навсегда.")
    else:
        await message.answer(f"{who} замучен на {duration_text}.")


@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "размут")
async def unmute_handler(message: Message, pool):
    if not await require_admin(message):
        return

    chat_id = message.chat.id
    user_id, display = await resolve_target_user(message, pool, username_pos=1)

    if not user_id:
        await message.answer("Укажи пользователя реплаем или так: `размут @username`.")
        return

    chat = await message.bot.get_chat(chat_id)
    default_perms = chat.permissions or ChatPermissions(can_send_messages=True)

    try:
        await message.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=default_perms,
            until_date=None
        )
    except TelegramBadRequest as e:
        await message.answer(tg_human_error(e))
        return

    await message.answer(f"{who_label(display)} размучен.")


# -------------------- BAN / UNBAN --------------------

@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "бан")
async def ban_handler(message: Message, pool):
    if not await require_admin(message):
        return

    chat_id = message.chat.id
    user_id, display = await resolve_target_user(message, pool, username_pos=1)

    if not user_id:
        await message.answer("Укажи пользователя реплаем или так: `бан @username 7д` (время опционально).")
        return

    if await deny_if_self(message, user_id, "забанить"):
        return

    args = get_args_after_target(message, username_pos=1)
    delta, duration_text, tail = split_duration_and_tail(args)

    reason = extract_reason(message, inline_tail=tail)

    until_date = None
    if delta is not None:
        until_date = datetime.now(timezone.utc) + delta

    try:
        await message.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            until_date=until_date
        )
    except TelegramBadRequest as e:
        await message.answer(tg_human_error(e))
        return

    who = who_label(display)
    if delta is None:
        if reason:
            await message.answer(f"{who} забанен.\nПричина: {reason}")
        else:
            await message.answer(f"{who} забанен.")
    else:
        if reason:
            await message.answer(f"{who} забанен на {duration_text}.\nПричина: {reason}")
        else:
            await message.answer(f"{who} забанен на {duration_text}.")


@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "разбан")
async def unban_handler(message: Message, pool):
    if not await require_admin(message):
        return

    chat_id = message.chat.id
    user_id, display = await resolve_target_user(message, pool, username_pos=1)

    if not user_id:
        await message.answer("Укажи пользователя реплаем или так: `разбан @username`.")
        return

    try:
        await message.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
    except TelegramBadRequest as e:
        await message.answer(tg_human_error(e))
        return

    await message.answer(f"{who_label(display)} разбанен.")


# -------------------- KICK (без бана) --------------------

@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "кик")
async def kick_handler(message: Message, pool):
    if not await require_admin(message):
        return

    chat_id = message.chat.id
    user_id, display = await resolve_target_user(message, pool, username_pos=1)

    if not user_id:
        await message.answer("Укажи пользователя реплаем или так: `кик @username`.")
        return

    if await deny_if_self(message, user_id, "кикнуть"):
        return

    try:
        # kick = ban + immediate unban
        await message.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        await message.bot.unban_chat_member(chat_id=chat_id, user_id=user_id, only_if_banned=True)
    except TelegramBadRequest as e:
        await message.answer(tg_human_error(e))
        return

    await message.answer(f"{who_label(display)} кикнут.")

