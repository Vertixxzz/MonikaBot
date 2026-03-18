from aiogram import Router
from aiogram.types import Message

import re

router = Router()

# ===================== CACHE =====================

# {chat_id: {trigger: (order, action)}}. да. это так же страшно понимать, как и читать
RP_COMMANDS: dict[int, dict[str, tuple[str, str]]] = {}

MAX_COMMANDS_PER_CHAT = 100
MIN_TRIGGER_LEN = 2
MAX_ACTION_LEN = 50

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

def get_target(message: Message):
    if not message.reply_to_message:
        return None
    return message.reply_to_message.from_user


def render(order: str, action: str, sender, target):
    if order == "12":
        return f"{sender.full_name} {action} {target.full_name}"
    elif order == "21":
        return f"{target.full_name} {action} {sender.full_name}"
    else:
        return "ошибка порядка"


# ===================== CREATE =====================

CREATE_REGEX = r'^сайори создать\s+"(.+?)"\s+"(12|21)"\s+"(.+?)"$'


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

    RP_COMMANDS.setdefault(chat_id, {})

    if trigger in RP_COMMANDS[chat_id]:
        await message.answer("Такая команда уже существует.")
        return

    if len(RP_COMMANDS[chat_id]) >= MAX_COMMANDS_PER_CHAT:
        await message.answer("Слишком много команд в чате.")
        return

    if len(action) > MAX_ACTION_LEN:
        await message.answer("Слишком длинное действие.")
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

    # --- обновление кэша ---
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

@router.message(lambda msg: msg.text == "сайори команды")
async def list_rp(message: Message):
    chat_id = message.chat.id

    if chat_id not in RP_COMMANDS or not RP_COMMANDS[chat_id]:
        await message.answer("Нет RP команд.")
        return

    cmds = list(RP_COMMANDS[chat_id].keys())

    await message.answer(
        "RP команды:\n" + "\n".join(cmds[:30])
    )


# ===================== RELOAD =====================

@router.message(lambda msg: msg.text == "сайори загрузи команды")
async def reload_rp(message: Message, pool):
    await load_rp_commands(pool)
    await message.answer("Команды перезагружены.")


# ===================== RP HANDLER =====================

@router.message(
    lambda msg: (
        msg.text
        and msg.chat.id in RP_COMMANDS
        and msg.text.lower().strip() in RP_COMMANDS[msg.chat.id]
    )
)
async def rp_handler(message: Message):
    chat_id = message.chat.id
    cmd = message.text.lower().strip()

    target = get_target(message)
    if not target:
        return

    sender = message.from_user

    order, action = RP_COMMANDS[chat_id][cmd]

    text = render(order, action, sender, target)

    await message.answer(text)