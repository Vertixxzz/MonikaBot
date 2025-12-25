from aiogram import Router, F
from aiogram.types import Message
from common.utils.links import get_bot_in_chat, BotNotFoundError
from common.db.economics import get_balance, add_balance
import random
import asyncio
import re

router = Router()

games: dict[int, dict] = {}

WORDS = [
    "монолит", "сайори", "монетка", "дружба", "поцелуй", "депрессия", "кухня", "счастье",
    "весна", "сервер", "объятие", "печенье", "котик", "суицид", "ывлатоп", "цхххххх","гидроцефал","барабарабарабереберебере"
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


def mask(word: str, guessed: set[str]) -> str:
    return " ".join(ch if ch in guessed else "_" for ch in word)


@router.message(F.text.lower().in_({"сайори повешайся", "сайори виселица"}))
async def start_hangman(message: Message, pool):
    chat_id = message.chat.id

    if chat_id in games:
        await message.reply("Эй, у нас уже идёт игра!")
        return

    word = random.choice(WORDS)
    state = {"word": word, "guessed": set(), "fails": 0, "monika_offer": False}
    games[chat_id] = state

    masked = mask(word, state["guessed"])

    if random.random() < 0.20:
        state["monika_offer"] = True
        await message.answer(
            f"Начнём игру в виселицу!\n{masked}\n\n"
            "Пиши буквы по одной."
        )
        try:
            monika = await get_bot_in_chat("monika", chat_id)
            await asyncio.sleep(0.6)
            await monika.send_message(
                chat_id,
                'эй. я тут! хочешь подскажу первую букву за 50 докидолларов? '
                'просто напиши "подсказка"'
            )
        except BotNotFoundError:
            await message.answer(
                'эм… кажется, Моника не может писать сюда. '
                'но если бы могла — она бы предложила "подсказка" за 50.'
            )
        except Exception as e:
            print(f"Ошибка при сообщении Моники: {e}")
    else:
        await message.answer(
            f"Начнём игру в виселицу!\n{masked}\n\n"
            "Пиши буквы по одной.\n"
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

    user_id = user.id
    username = user.username or user.first_name

    balance = await get_balance(pool, user_id)
    if balance < 50:
        await message.reply("у тебя настолько все плохо с бюджетом? надо пить меньше пива, друг.")
        return

    await add_balance(pool, user_id, username, -50)

    word = state["word"]
    first = word[0]
    state["guessed"].add(first)
    masked = mask(word, state["guessed"])

    try:
        monika = await get_bot_in_chat("monika", chat_id)
        await monika.send_message(
            chat_id,
            f"первая буква — **{first.upper()}**. никому не говори~"
        )
    except BotNotFoundError:
        await message.answer(f"первая буква — **{first.upper()}**")
    except Exception as e:
        print(f"Ошибка при подсказке от Моники: {e}")


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

    if letter not in word:
        state["fails"] += 1
        comment = random.choice(["ой... не то", "не угадал~", "нет такой буквы "])
    else:
        comment = random.choice(["правильно!", "отлично идёшь!", "так держать!"])

    masked = mask(word, state["guessed"])
    fails = state["fails"]
    max_fails = len(HANGMAN) - 1

    # победа
    if set(word) <= state["guessed"]:
        await message.answer(
            f"{masked}\n Победа! \nТы спас человечка!!"
        )

        user = message.from_user
        if user:
            await add_balance(pool, user.id, user.username or user.first_name, +0)
            await message.answer("Извини, у меня кончились Докидоллары! Но поздравляю с победой ")
        games.pop(chat_id, None)
        return

    # проигрыш
    if fails >= max_fails:
        await message.answer(f"{HANGMAN[-1]}\nПроиграли...\nСлово было: *{word}*")
        games.pop(chat_id, None)
        return

    await message.answer(f"{HANGMAN[fails]}\n{masked}\n{comment}\nОшибки: {fails}/{max_fails}")

    @router.message(F.text.lower().regexp(r"^сайори слово\s+(.+)$"))
    async def guess_whole_word(message: Message, pool):
        chat_id = message.chat.id
        state = games.get(chat_id)
        if not state:
            await message.reply("мы не играем сейчас~ начни с «сайори виселица».")
            return

        match = re.match(r"^сайори слово\s+(.+)$", message.text.strip(), re.IGNORECASE)
        attempt = match.group(1).strip().lower()

        word = state["word"]

        # если угадали
        if attempt == word:
            masked = mask(word, set(word))
            await message.answer(
                "Извини, у меня кончились Докидоллары! Но поздравляю с победой"
            )

            user = message.from_user
            if user:
                await add_balance(pool, user.id, user.username or user.first_name, +0)

            games.pop(chat_id, None)
            return

        # если ошибся
        await message.answer(
            f"Нет… слово было **{word}**.\n"
            "Игра окончена моментально."
        )

        games.pop(chat_id, None)
