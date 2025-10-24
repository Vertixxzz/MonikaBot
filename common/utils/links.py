from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

bots: dict[str, Bot] = {}

def register_bot(name: str, bot: Bot):
    bots[name.lower()] = bot

def get_bot(name: str) -> Bot:
    bot = bots.get(name.lower())
    if bot is None:
        raise BotNotFoundError(f"Бот '{name}' не зарегистрирован.")
    return bot


class BotNotFoundError(Exception):
    pass


async def get_bot_in_chat(name: str, chat_id: int) -> Bot:
    name = name.lower()
    bot = get_bot(name)
    if bot is None:
        raise BotNotFoundError(f"Бот '{name}' не зарегистрирован.")

    try:
        member = await bot.get_chat_member(chat_id, bot.id)
        if member.status not in ("member", "administrator", "creator"):
            raise BotNotFoundError(f"Бот '{name}' не находится в чате {chat_id}.")
    except (TelegramForbiddenError, TelegramBadRequest):
        raise BotNotFoundError(f"Бот '{name}' не находится в чате {chat_id}.")
    except Exception as e:
        raise BotNotFoundError(f"Ошибка при проверке бота '{name}': {e}")

    return bot