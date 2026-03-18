import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram.types import Message, ChatPermissions
from aiogram.exceptions import TelegramBadRequest

from common.db.utilities import get_user_id_by_username

MSK = ZoneInfo("Europe/Moscow")
ADMIN_STATUSES = ("administrator", "creator")


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
        return "Нельзя применить действие к владельцу чата."
    if "participant_id_invalid" in msg:
        return "Ты указал неправильного пользователя или не указал его вовсе."
    return f"Ошибка Telegram: {getattr(e, 'message', str(e))}"


async def deny_if_self(message: Message, target_id: int, action_word: str) -> bool:
    if target_id == message.bot.id:
        await message.answer(f"Эй! {action_word} меня — ужасный выбор!")
        return True
    return False


async def resolve_target_user(
    message: Message,
    pool,
    username_pos: int = 1,
) -> tuple[int | None, str | None]:
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


def parse_duration(text: str) -> timedelta:
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
        re.IGNORECASE,
    )

    matches = pattern.findall(text)
    if not matches:
        raise ValueError("Я не смогла понять длительность.")

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
        raise ValueError("Длительность должна быть больше нуля.")

    return total


def extract_reason_from_second_line(message: Message) -> str | None:
    lines = (message.text or "").splitlines()
    if len(lines) >= 2 and lines[1].strip():
        return lines[1].strip()
    return None


def get_args_after_target(message: Message, username_pos: int = 1) -> list[str]:
    first_line = (message.text or "").splitlines()[0].strip()
    parts = first_line.split()

    if message.reply_to_message:
        start = 1
    else:
        start = username_pos + 1

    return parts[start:] if len(parts) > start else []


def split_duration_and_tail(args: list[str]) -> tuple[timedelta | None, str, str]:
    if not args:
        return None, "", ""

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