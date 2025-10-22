from aiogram import Router, F
from aiogram.types import Message
from common.utils.links import get_bot
from common.utils.isshehere import check_monika_present
import random
import asyncio
from cfg import NONRP, NON18RP
import time
router = Router()

async def isrpable(message: Message, target) -> bool:
    if target.id in NONRP:
        await message.reply("Этот человек не хочет, чтобы с ним выполняли ролевые действия")
        return False
    return True

async def is18rpable(message: Message, target) -> bool:
    if target.id in NONRP:
        await message.reply("этот человек не хочет, чтоб с ним выполняли 18+ ролевые действия")
        return False
    if target in NON18RP:
        await message.reply("этот человек не хочет, чтоб с ним выполняли 18+ ролевые действия")
        return False
    return True

@router.message(F.text.lower().in_({"обнял", "обняла", "обнять"}))
async def rp_hug(message: Message):
    if not message.reply_to_message:
        return

    sender = message.from_user
    target = message.reply_to_message.from_user or message.reply_to_message.sender_chat
    if not (sender and target and hasattr(target, "id")):
        return

    if not await isrpable(message, target):
        return

    name1 = sender.username or sender.first_name
    name2 = target.username or target.first_name

    if name1 == name2:
        await message.reply("Охх.. ты хочешь обнять себя? Давай лучше.. я тебя обниму?")
        await asyncio.sleep(2)
        await message.answer(f"Я заключила в объятия @{name1}!")
        return

    if target.id == 7965136625:
        await message.reply("М.. меня? Ты хочешь обнять меня? Я только рада!!")
        await asyncio.sleep(2)

        rando = random.randint(1, 100)
        if rando > 0:
            monika = get_bot("monika")
            if monika:
                present = await check_monika_present(message.chat.id)
                if present:
                    try:
                        await monika.send_message(
                            message.chat.id,
                            f"*подглядывает*"
                        )
                    except Exception as e:
                        pass
    print("target.id:", target.id, "target.username:", target.username)

    if target.id == 8324502664:
        monika = get_bot("monika")
        if monika:
            try:
                await monika.send_message(
                    message.chat.id,
                    "ну наконец-то моя очередь!"
                )
                await message.reply(
                    "кхехе, Моника так смешно выглядит, когда её кто-то обнимает!"
                )
            except Exception as e:
                print("Ошибка при отправке от Моники:", e)

    if not await isrpable(message, target):
        return

    await message.answer(f"@{name2} заключен(а) в объятиях @{name1}!")

@router.message(F.text.lower().in_({"убил", "убила", "убить"}))
async def rp_kill(message: Message):
    if not message.reply_to_message:
        return

    sender = message.from_user
    target = message.reply_to_message.from_user or message.reply_to_message.sender_chat
    if not (sender and target and hasattr(target, "id")):
        return

    name1 = sender.username or sender.first_name
    name2 = getattr(target, "username", None) or getattr(target, "title", None) or "Нету у него имени"

    monika = get_bot("monika")
    chat_id = message.chat.id

    if not await isrpable(message, target):
        return

    if not await is18rpable(message, target):
        return

    if target.id == 7965136625:
        await message.reply("...")
        await asyncio.sleep(1)
        await message.answer("ты... серьёзно?..")
        await asyncio.sleep(1.5)
        rand2 = random.randint(1, 100)
        if rand2 > 80:
            if monika:
                try:
                    await monika.send_message(
                        chat_id,
                        f"@{name1}... Зачем? Разве тебе не хватило того, что когда-то сделала я?"
                    )
                except Exception as e:
                    print("Ошибка при ответе Моники:", e)

        await asyncio.sleep(2)
        await message.answer(f"@{name1} убил(а) @{name2}...")
        await asyncio.sleep(5)
        await message.answer(f"Но я всегда возвращаюсь! Хехехе")
        return

    if target.id == 8324502664:
        if monika:
            try:
                try:
                    await monika.ban_chat_member(chat_id, sender.id)
                    await monika.send_message(
                        chat_id,
                        f"@{name1} попытался(ась) убить Монику... и теперь исчез навсегда"
                    )
                except Exception:
                    await monika.send_message(
                        chat_id,
                        f"Было бы у меня достаточно прав... @{name1}"
                    )
            except Exception as e:
                print("Ошибка при ответе Моники:", e)
        return

    phrases = [
        f"@{name1} хладнокровно убил(а) @{name2}.",
        f"@{name2} не успел(а) даже вскрикнуть - @{name1} оказался(ась) быстрее.",
        f"Кровь, крик и... тишина. {name1} убил(а) @{name2}.",
    ]
    await message.answer(random.choice(phrases))

    rand = random.randint(0, 100)
    if rand > 80:
        if monika:
            try:
                await monika.send_message(
                    chat_id,
                    f"Жесть.. в вашем мире убить кого-то это так.. тяжело?"
                )
            except Exception:
                pass