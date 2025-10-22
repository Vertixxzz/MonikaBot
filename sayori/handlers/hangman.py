from aiogram import Router, F
from aiogram.types import Message
import random

router = Router()

# Хранилище игр: chat_id -> {word, guessed, fails}
games = {}

WORDS = [
    "монолит", "сайори", "монетка", "пирожок", "дружба", "поцелуй",
    "весна", "тревога", "котик", "сервер", "объятие", "печенье"
]

HANGMAN = [
    "```\n\n\n\n\n```",
    "```\n\n\n\n\n====```",
    "```\n O\n\n\n\n====```",
    "```\n O\n |\n\n\n====```",
    "```\n O\n/|\n\n\n====```",
    "```\n O\n/|\\\n\n\n====```",
    "```\n O\n/|\\\n/\n====```",
    "```\n O\n/|\\\n/ \\\n====```",
]


def get_mask(word: str, guessed: set[str]) -> str:
    return " ".join(ch if ch in guessed else "_" for ch in word)


@router.message(F.text.lower().in_({"/виселица", "виселица"}))
async def start_hangman(message: Message):
    """Начинает новую игру"""
    if message.chat.id in games:
        await message.reply("Эй, у нас уже идёт игра! 😅")
        return

    word = random.choice(WORDS)
    games[message.chat.id] = {"word": word, "guessed": set(), "fails": 0}

    masked = get_mask(word, set())
    await message.answer(
        f"Начнём игру в виселицу! 🎀\n"
        f"{masked}\n\n"
        "Пиши буквы по одной. Только не ошибайся слишком часто... 😰"
    )


@router.message(F.text.regexp("^[а-яА-Яa-zA-Z]$"))
async def guess_letter(message: Message):
    """Обрабатывает ввод буквы"""
    game = games.get(message.chat.id)
    if not game:
        return  # игры нет

    letter = message.text.lower()
    if letter in game["guessed"]:
        await message.reply("Ты уже пробовал эту букву~ 😅")
        return

    game["guessed"].add(letter)
    word = game["word"]

    if letter not in word:
        game["fails"] += 1
        comment = random.choice([
            "Ой... не то 😖",
            "Хах, не угадал~",
            "Нет, такой буквы нет 😔",
            "Эм... попробуй другую?",
        ])
    else:
        comment = random.choice([
            "О! Правильно! 🌸",
            "Ура, буква на месте!",
            "Вот теперь я начинаю верить в тебя~ 💫",
        ])

    masked = get_mask(word, game["guessed"])
    fails = game["fails"]

    if set(word) <= game["guessed"]:
        await message.answer(
            f"{masked}\n✨ Победа! ✨\n"
            f"Ты спас маленького человечка! (и меня тоже чуть-чуть 🌸)"
        )
        games.pop(message.chat.id)
    elif fails >= len(HANGMAN) - 1:
        await message.answer(
            f"{HANGMAN[-1]}\n"
            f"😢 Проиграли...\n"
            f"Слово было: *{word}*"
        )
        games.pop(message.chat.id)
    else:
        await message.answer(
            f"{HANGMAN[fails]}\n{masked}\n{comment}\nОшибки: {fails}/{len(HANGMAN) - 1}"