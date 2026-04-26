from aiogram import Router
from aiogram.types import Message

import re
import html

router = Router()

# ===================== CACHE =====================

# {chat_id: {trigger: (order, action)}} это так же страшно понимать, как и читать
RP_COMMANDS: dict[int, dict[str, tuple[str, str]]] = {}
FORBIDDEN = ["мут", "бан", "варн", "кик"]

MAX_COMMANDS_PER_CHAT = 100
MIN_TRIGGER_LEN = 2
MAX_ACTION_LEN = 50

CREATE_REGEX = r'^сайори создать\s+"(.+?)"\s+"(12|21)"\s+"(.+?)"$'


# ===================== LOAD =====================

async def load_rp_commands(pool):
    rows = await pool.fetch(
        "SELECT chat_id, trigger, user_order, action FROM rp_commands"
    )

    RP_COMMANDS.clear()

    for r in rows:
        chat_id = r["chat_id"]
        trigger = r["trigger"]
        order = r["user_order"]
        action = r["action"]

        RP_COMMANDS.setdefault(chat_id, {})
        RP_COMMANDS[chat_id][trigger] = (order, action)


# ===================== HELPERS =====================

def mention(user_id: int, username: str):
    return f'<a href="tg://user?id={user_id}">@{html.escape(username)}</a>'


async def is_admin(message: Message) -> bool:
    member = await message.bot.get_chat_member(
        message.chat.id,
        message.from_user.id
    )
    return member.status in ("administrator", "creator")


async def resolve_target(message: Message, pool):
    # 1. reply
    if message.reply_to_message:
        u = message.reply_to_message.from_user

        if not u or not u.username:
            await message.answer("У пользователя нет username.")
            return None

        return u.id, u.username

    # 2. @username
    parts = message.text.split()

    if len(parts) >= 2:
        username = parts[1].lstrip("@").lower()

        from common.db.utilities import get_user_id_by_username

        user_id = await get_user_id_by_username(pool, username)
        if not user_id:
            await message.answer("Пользователь не найден.")
            return None

        return user_id, username

    return None


def render(order: str, action: str, sender, target_id, target_username):
    m_sender = mention(sender.id, sender.username or sender.first_name)
    m_target = mention(target_id, target_username)

    if order == "12":
        return f"{m_sender} {action} {m_target}"
    elif order == "21":
        return f"{m_target} {action} {m_sender}"


# ===================== CREATE =====================

@router.message(lambda msg: msg.text and msg.text.lower().startswith("сайори создать"))
async def create_rp(message: Message, pool):
    text = message.text.strip()

    match = re.match(CREATE_REGEX, text, re.IGNORECASE)
    if not match:
        await message.answer(
            'Использование:\n'
            'сайори создать "триггер" "12|21" "действие"\n\n'
            'Пример:\n'
            'сайори создать "обнять" "12" "обнял"'
        )
        return

    trigger, order, action = match.groups()

    trigger = trigger.lower().strip()
    action = action.strip()
    chat_id = message.chat.id

    # --- валидация ---
    if len(trigger) < MIN_TRIGGER_LEN:
        await message.answer("Слишком короткий триггер.")
        return

    if len(action) > MAX_ACTION_LEN:
        await message.answer(f"Слишком длинное действие (макс {MAX_ACTION_LEN}).")
        return

    RP_COMMANDS.setdefault(chat_id, {})

    if trigger in RP_COMMANDS[chat_id]:
        await message.answer("Такая команда уже существует.")
        return

    if len(RP_COMMANDS[chat_id]) >= MAX_COMMANDS_PER_CHAT:
        await message.answer("Слишком много команд в чате.")
        return

    if trigger in FORBIDDEN:
        await message.answer("Ага! захотел!")
        return


    # --- запись ---
    await pool.execute(
        """
        INSERT INTO rp_commands (chat_id, trigger, user_order, action, created_by)
        VALUES ($1, $2, $3, $4, $5)
        """,
        chat_id,
        trigger,
        order,
        action,
        message.from_user.id,
    )

    # --- кэш ---
    RP_COMMANDS[chat_id][trigger] = (order, action)

    await message.answer(f"Команда '{trigger}' создана.")


# ===================== DELETE =====================

@router.message(lambda msg: msg.text and msg.text.lower().startswith("сайори удалить"))
async def delete_rp(message: Message, pool):
    parts = message.text.split()

    if len(parts) < 3:
        await message.answer("Использование: сайори удалить <триггер>")
        return

    trigger = parts[2].lower().strip()
    chat_id = message.chat.id

    if chat_id not in RP_COMMANDS or trigger not in RP_COMMANDS[chat_id]:
        await message.answer("Такой команды нет.")
        return

    await pool.execute(
        "DELETE FROM rp_commands WHERE chat_id = $1 AND trigger = $2",
        chat_id,
        trigger,
    )

    RP_COMMANDS[chat_id].pop(trigger, None)

    await message.answer(f"Команда '{trigger}' удалена.")


# ===================== LIST =====================

@router.message(lambda msg: msg.text and msg.text.lower().startswith("сайори команды"))
async def list_rp(message: Message):
    chat_id = message.chat.id

    if chat_id not in RP_COMMANDS or not RP_COMMANDS[chat_id]:
        await message.answer("Нет RP команд.")
        return

    cmds = list(RP_COMMANDS[chat_id].keys())

    await message.answer("RP команды:\n" + "\n".join(cmds[:30]))


# ===================== RELOAD (ADMIN ONLY) =====================

@router.message(lambda msg: msg.text == "сайори загрузи команды")
async def reload_rp(message: Message, pool):
    if not await is_admin(message):
        await message.answer("Только администраторы могут перезагружать команды.")
        return

    await load_rp_commands(pool)
    await message.answer("Команды перезагружены.")


# ===================== RP HANDLER =====================

@router.message(
    lambda msg: (
        msg.text
        and msg.chat.id in RP_COMMANDS
        and msg.text.split()[0].lower() in RP_COMMANDS[msg.chat.id]
    )
)
async def rp_handler(message: Message, pool):
    parts = message.text.split()
    cmd = parts[0].lower()
    chat_id = message.chat.id

    sender = message.from_user
    if not sender:
        return

    target_data = await resolve_target(message, pool)
    if not target_data:
        return

    target_id, target_username = target_data

    order, action = RP_COMMANDS[chat_id][cmd]

    text = render(order, action, sender, target_id, target_username)

    await message.answer(text, parse_mode="HTML")