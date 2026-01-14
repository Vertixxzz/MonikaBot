from __future__ import annotations

import asyncio
import random
import re
from typing import Any

from aiogram import Router, F
from aiogram.types import Message

from common.utils.links import get_bot_in_chat, BotNotFoundError
from common.db.economics import get_balance, add_balance
from common.db.hangman_daily import today_msk_date, try_consume_game, get_remaining_games

router = Router()

games: dict[int, dict[str, Any]] = {}

DAILY_GAMES_LIMIT = 3

DIFF_ALIASES = {
    "легко": "easy",
    "лёгко": "easy",
    "изи": "easy",
    "easy": "easy",

    "норм": "normal",
    "нормально": "normal",
    "средне": "normal",
    "normal": "normal",

    "сложно": "hard",
    "хард": "hard",
    "трудно": "hard",
    "hard": "hard",
}


def parse_diff(text: str | None) -> str:
    if not text:
        return "normal"
    t = text.strip().lower()
    return DIFF_ALIASES.get(t, "normal")


WORDS_EASY = [
    "монолит", "монетка", "дружба", "поцелуй", "кухня", "счастье",
    "весна", "сервер", "объятие", "печенье", "котик",
    "домик", "яблоко", "машина", "кофе", "чайник", "подушка",
    "солнышко", "улыбка", "цветок", "молоко", "каша",
    "письмо", "игрушка", "кровать", "окно", "дверь",
    "листик", "трава", "река", "море", "рыбка", "птичка",
    "шапка", "куртка", "ботинки", "рюкзак",
    "карандаш", "тетрадь", "книга", "журнал",
    "фонарь", "лампа", "столик", "стул",
    "телефон", "плеер", "наушники",
    "печка", "чай", "сахар", "конфета",
    "подарок", "праздник", "вечеринка",
]

WORDS_NORMAL = [
    "сайори", "депрессия",
    "параллель", "клавиатура", "программа", "алгоритм",
    "реальность", "самочувствие", "настроение",
    "психология", "сообщество", "компьютер",
    "хаотичность", "перегрузка", "бессонница",
    "шизофрения", "экзистенция",
    "неопределенность",
    "раздражение",
    "усталость",
    "самооценка",
    "сомнение",
    "переживание",
    "замешательство",
    "противоречие",
    "взаимодействие",
    "сопротивление",
    "преувеличение",
    "невнимательность",
    "многозадачность",
    "непоследовательность",
    "разочарование",
    "криволинейность",
    "дисбаланс",
    "хаотизация",
    "декомпозиция",

]

WORDS_HARD = [
    "гидроцефал",
    "барабарабараберебереберебере",
    "псевдопсевдогипопаратиреоз",
    "гиперчувствительность",
    "квазиэкспериментальный",
    "деинституционализация",
    "флуоресценция",
    "электрофизиология",
    "экстраполяция",
    "сверхвысокочастотный",
    "дезоксирибонуклеиновый",
    "антидизестаблишментарианизм",
    "переосвидетельствование",
    "высококвалифицированный",
    "междисциплинарность",
    "контрреволюционирование",
    "сверхинтерпретация",
    "псевдонаучность",
    "гиперболизированный",
    "экспоненциальность",
    "децентрализация",
    "мультиколлинеарность",
    "фотоэлектрохимический",
    "радиоэлектроаппаратура",
    "синхрофазотрон",
    "квазигосударственность",
    "чрезвычайнонепредсказуемый",
    "самоидентифицирующийся",
]

DIFFICULTIES = {
    "easy":   {"reward": 100, "wrong_penalty": 1, "max_fails": 7, "words": WORDS_EASY, "hint_cost": 50},
    "normal": {"reward": 200, "wrong_penalty": 1, "max_fails": 7, "words": WORDS_NORMAL, "hint_cost": 50},
    "hard":   {"reward": 500, "wrong_penalty": 2, "max_fails": 7, "words": WORDS_HARD, "hint_cost": 50},  # hard +2 fail
}

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


def mask(word: str, guessed: set[str]) -> str:
    return " ".join(ch if ch in guessed else "_" for ch in word)


@router.message(F.text.regexp(r"(?i)^сайори\s+виселица(?:\s+\S+)?$"))
async def start_hangman(message: Message, pool):
    user = message.from_user
    if not user:
        return

    chat_id = message.chat.id
    if chat_id in games:
        await message.reply("Эй, у нас уже идёт игра!")
        return

    raw = (message.text or "").strip()
    m = re.match(r"(?i)^сайори\s+виселица(?:\s+(\S+))?$", raw)
    diff_arg = m.group(1) if m else None
    diff = parse_diff(diff_arg)

    day = today_msk_date()
    ok, remaining_paid = await try_consume_game(pool, user.id, day, DAILY_GAMES_LIMIT)
    paid = bool(ok)
    if not paid:
        remaining_paid = 0

    word = random.choice(DIFFICULTIES[diff]["words"])
    state = {
        "word": word,
        "guessed": set(),
        "fails": 0,
        "monika_offer": False,
        "difficulty": diff,
        "paid": paid,
        "owner_id": user.id,
        "owner_name": user.username or user.first_name,
    }
    games[chat_id] = state

    masked = mask(word, state["guessed"])

    payline = (
        f"Эта игра оплачиваемая. Осталось оплачиваемых игр сегодня: {remaining_paid}"
        if paid else
        "Оплачиваемые игры на сегодня закончились - докидолларов я тебе за нее не дам"
    )

    if random.random() < 0.20:
        state["monika_offer"] = True
        await message.answer(
            f"Начнём игру в виселицу! (сложность: {diff_arg or 'средняя'})\n"
            f"{masked}\n\n"
            "Пиши буквы по одной.\n"
            f"{payline}"
        )
        try:
            monika = await get_bot_in_chat("monika", chat_id)
            await asyncio.sleep(0.6)
            cost = DIFFICULTIES[diff]["hint_cost"]
            await monika.send_message(
                chat_id,
                f'эй. я тут! хочешь подскажу первую букву за {cost} докидолларов? '
                'просто напиши "подсказка"'
            )
        except BotNotFoundError:
            cost = DIFFICULTIES[diff]["hint_cost"]
            await message.answer(
                'эм… кажется, Моника не может писать сюда. '
                f'но если бы могла - она бы предложила "подсказка" за {cost}.'
            )
        except Exception as e:
            print(f"Ошибка при сообщении Моники: {e}")
    else:
        await message.answer(
            f"Начнём игру в виселицу! (сложность: {diff_arg or 'средняя'})\n"
            f"{masked}\n\n"
            "Пиши буквы по одной.\n"
            f"{payline}"
        )


@router.message(F.text.lower() == "подсказка")
async def ask_hint(message: Message, pool):
    chat_id = message.chat.id
    state = games.get(chat_id)
    if not state:
        return

    if not state.get("monika_offer"):
        await message.reply("хм? я не даю подсказок, хехе")
        return

    user = message.from_user
    if not user:
        return

    diff = state.get("difficulty", "normal")
    cost = DIFFICULTIES[diff]["hint_cost"]

    balance = await get_balance(pool, user.id)
    if balance < cost:
        await message.reply("у тебя настолько все плохо с бюджетом? надо пить меньше пива, друг.")
        return

    await add_balance(pool, user.id, user.username or user.first_name, -cost)

    word = state["word"]
    first = word[0]
    state["guessed"].add(first)
    masked = mask(word, state["guessed"])

    try:
        monika = await get_bot_in_chat("monika", chat_id)
        await monika.send_message(chat_id, f"первая буква - {first.upper()}. никому не говори~")
    except BotNotFoundError:
        await message.answer(f"первая буква - {first.upper()}")
    except Exception as e:
        print(f"Ошибка при подсказке от Моники: {e}")

    await message.answer(masked)


@router.message(F.text.regexp(r"^[а-яА-Яa-zA-Z]$"))
async def guess_letter(message: Message, pool):
    chat_id = message.chat.id
    state = games.get(chat_id)
    if not state:
        return

    letter = (message.text or "").lower()
    if letter in state["guessed"]:
        await message.reply("ты уже пробовал эту букву~")
        return

    state["guessed"].add(letter)
    word = state["word"]
    diff = state.get("difficulty", "normal")

    if letter not in word:
        penalty = DIFFICULTIES[diff]["wrong_penalty"]  # hard = 2
        state["fails"] += penalty
        comment = random.choice(["ой... не то", "не угадал~", "нет такой буквы "])
    else:
        comment = random.choice(["правильно!", "отлично идёшь!", "так держать!"])

    masked = mask(word, state["guessed"])
    fails = state["fails"]
    max_fails = DIFFICULTIES[diff]["max_fails"]

    # Победа
    if set(word) <= state["guessed"]:
        await message.answer(f"{masked}\nПобеда! Ты спас человечка!!")

        owner_id = int(state["owner_id"])
        owner_name = str(state["owner_name"])
        paid = bool(state.get("paid"))

        if paid:
            reward = DIFFICULTIES[diff]["reward"]
            await add_balance(pool, owner_id, owner_name, +reward)

            day = today_msk_date()
            remaining = await get_remaining_games(pool, owner_id, day, DAILY_GAMES_LIMIT)
            await message.answer(
                f"Это была оплачиваемая игра\n"
                f"+{reward} докидолларов\n"
                f"у тебя осталось {remaining} оплачиваемых игр на сегодня (по МСК)."
            )
        else:
            await message.answer("Увыыы, но докидолларов я тебе за эту игру не дам - вернись завтра!")

        games.pop(chat_id, None)
        return

    # Проигрыш
    if fails >= max_fails:
        await message.answer(f"{HANGMAN[-1]}\nПроиграли...\nСлово было: *{word}*")

        owner_id = int(state["owner_id"])
        paid = bool(state.get("paid"))
        if paid:
            day = today_msk_date()
            remaining = await get_remaining_games(pool, owner_id, day, DAILY_GAMES_LIMIT)
            await message.answer(
                f"Это была оплачиваемая игра, но ты проиграл, увы!.\n"
                f"у тебя осталось {remaining} оплачиваемых игр на сегодня."
            )
        else:
            await message.answer("Игра была неоплачиваемая и.. тебе все же удалось проиграть")

        games.pop(chat_id, None)
        return

    hang_i = min(fails, len(HANGMAN) - 1)
    await message.answer(f"{HANGMAN[hang_i]}\n{masked}\n{comment}\nОшибки: {fails}/{max_fails}")


@router.message(F.text.lower().regexp(r"^сайори\s+слово\s+.+$"))
async def guess_whole_word(message: Message, pool):
    chat_id = message.chat.id
    state = games.get(chat_id)
    if not state:
        await message.reply("мы не играем сейчас~ начни с «сайори виселица».")
        return

    raw = (message.text or "").strip()
    match = re.match(r"(?i)^сайори\s+слово\s+(.+)$", raw)
    if not match:
        return

    attempt = match.group(1).strip().lower()
    word = state["word"]
    diff = state.get("difficulty", "normal")
    paid = bool(state.get("paid"))

    owner_id = int(state["owner_id"])
    owner_name = str(state["owner_name"])

    if attempt == word:
        masked = mask(word, set(word))
        await message.answer(f"{masked}\nПобеда! Ты угадал слово целиком!!")

        if paid:
            reward = DIFFICULTIES[diff]["reward"]
            await add_balance(pool, owner_id, owner_name, +reward)

            day = today_msk_date()
            remaining = await get_remaining_games(pool, owner_id, day, DAILY_GAMES_LIMIT)
            await message.answer(
                f"Это была оплачиваемая игра \n"
                f"+{reward} докидолларов\n"
                f"у тебя осталось {remaining} оплачиваемых игр на сегодня (по МСК)."
            )
        else:
            await message.answer("Увыыы, но докидолларов я тебе за эту игру не дам - вернись завтра!")

        games.pop(chat_id, None)
        return

    await message.answer(f"Нет… слово было {word}.\nИгра окончена моментально.")

    if paid:
        day = today_msk_date()
        remaining = await get_remaining_games(pool, owner_id, day, DAILY_GAMES_LIMIT)
        await message.answer(
            f"Это была оплачиваемая игра, но ты проиграл, увы!.\n"
            f"у тебя осталось {remaining} оплачиваемых игр на сегодня"
        )
    else:
        await message.answer("За эту игру докидолларов я тебе не дам, хехе")

    games.pop(chat_id, None)
