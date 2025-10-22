from typing import Dict
from aiogram import Bot

bots: Dict[str, Bot] = {}


def register_bot(name: str, bot: Bot):
    bots[name.lower()] = bot


def get_bot(name: str) -> Bot | None:
    return bots.get(name.lower())