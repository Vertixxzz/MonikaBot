from aiogram import Router, F
from aiogram.types import Message
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from common.utils.links import get_bot_in_chat, BotNotFoundError
from cfg import NONRP, NON18RP, ADMIN_LIST
import asyncio
import random

router = Router()

async def isrpable(message: Message, target, sender) -> bool:
    if target.id in NONRP or sender.id in NONRP:
        await message.reply("Этот человек не хочет, чтобы с ним выполняли ролевые действия.")
        return False
    return True


async def is18rpable(message: Message, target, sender) -> bool:
    if target.id in NON18RP or sender.id in NON18RP:
        await message.reply("Этот человек не хочет, чтоб с ним выполняли 18+ ролевые действия.")
        return False
    return True


# --- RP команды --- #
@router.message(F.text.lower().in_({"обнял", "обняла", "обнять"}))
async def rp_hug(message: Message):
    if not message.reply_to_message:
        return

    sender = message.from_user
    target = message.reply_to_message.from_user or message.reply_to_message.sender_chat
    if not target or not hasattr(target, "id"):
        return

    if not await isrpable(message, target, sender):
        return

    name1 = sender.username or sender.first_name
    name2 = getattr(target, "username", None) or getattr(target, "first_name", None) or getattr(target, "title", "Безымянный")
    chat_id = message.chat.id

    if name1 == name2:
        await message.reply("Охх... ты хочешь обнять себя? Давай лучше... я тебя обниму ❤️")
        await asyncio.sleep(2)
        await message.answer(f"Я заключила в объятия @{name1}!")
        return

    if target.id == 7965136625:
        await message.reply("М... меня? Ты хочешь обнять меня? Я только рада!!")
        await asyncio.sleep(2)
        try:
            monika = await get_bot_in_chat("monika", chat_id)
            await monika.send_message(chat_id, "*подглядывает*")
        except BotNotFoundError:
            pass
        except Exception:
            pass

    elif target.id == 8324502664:
        try:
            monika = await get_bot_in_chat("monika", chat_id)
            await monika.send_message(chat_id, "ну наконец-то моя очередь!")
            await message.reply("кхехе, Моника так смешно выглядит, когда её кто-то обнимает!")
        except BotNotFoundError:
            await message.reply("Моники нет в чате, но представим, что она тоже улыбается~")
        except Exception as e:
            print("Ошибка при ответе Моники:", e)

    await message.answer(f"@{name2} заключен(а) в объятиях @{name1}!")


@router.message(F.text.lower().in_({"убил", "убила", "убить"}))
async def rp_kill(message: Message):
    if not message.reply_to_message:
        return

    sender = message.from_user
    target = message.reply_to_message.from_user or message.reply_to_message.sender_chat
    if not target or not hasattr(target, "id"):
        return

    chat_id = message.chat.id
    name1 = sender.username or sender.first_name
    name2 = getattr(target, "username", None) or getattr(target, "first_name", None) or getattr(target, "title", "Безымянный")

    if not await isrpable(message, target, sender):
        return
    if not await is18rpable(message, target, sender):
        return

    if name1 == name2:
        await message.reply("Охохо... это косплей на меня? Я очень ценю, но пожалуйста... не делай так.")
        await message.reply(f"@{name1} остался жив и здоров!")
        return

    if target.id == 7965136625:
        await message.reply("...")
        await asyncio.sleep(1)
        await message.answer("ты... серьёзно?..")
        await asyncio.sleep(1.5)
        try:
            monika = await get_bot_in_chat("monika", chat_id)
            if random.randint(1, 100) > 80:
                await monika.send_message(chat_id, f"@{name1}... Зачем? Разве тебе не хватило того, что когда-то сделала я?")
        except BotNotFoundError:
            pass
        except Exception as e:
            print("Ошибка при ответе Моники:", e)

        await asyncio.sleep(2)
        await message.answer(f"@{name1} убил(а) @{name2}...")
        return

    if target.id == 8324502664:
        try:
            monika = await get_bot_in_chat("monika", chat_id)
            await monika.ban_chat_member(chat_id, sender.id)
            await message.reply(f"@{name1} попытался(ась) убить Монику... и теперь исчез навсегда.")
        except TelegramBadRequest:
            await monika.send_message(chat_id, f"Было бы у меня достаточно прав... @{name1}")
        except BotNotFoundError:
            await message.reply("Ты.. пытаешься убить бота, которого нет в чате? Сильно..")
        except Exception as e:
            print(f"Ошибка при обработке убийства Моники: {e}")
        return

    phrases = [
        f"@{name1} хладнокровно убил(а) @{name2}.",
        f"@{name2} не успел(а) даже вскрикнуть — @{name1} оказался(ась) быстрее.",
        f"Кровь, крик и... тишина. @{name1} убил(а) @{name2}.",
    ]
    await message.answer(random.choice(phrases))

    try:
        monika = await get_bot_in_chat("monika", chat_id)
        if random.randint(0, 100) > 80:
            await monika.send_message(chat_id, "Жесть... в вашем мире убить кого-то это так... тяжело?")
    except BotNotFoundError:
        pass
    except Exception:
        pass


@router.message(F.text.lower().in_({"поцеловать", "поцеловал", "поцеловала"}))
async def rp_kiss(message: Message):
    if not message.reply_to_message:
        return

    sender = message.from_user
    target = message.reply_to_message.from_user or message.reply_to_message.sender_chat
    if not target or not hasattr(target, "id"):
        return

    name1 = sender.username or sender.first_name
    name2 = getattr(target, "username", None) or getattr(target, "first_name", None) or getattr(target, "title", "Безымянный")
    chat_id = message.chat.id

    if not await isrpable(message, target, sender):
        return

    if name1 == name2:
        await message.reply("Ты... пытаешься поцеловать себя? Ну... ладно.")
        return

    if target.id == 7965136625:
        if sender.id not in ADMIN_LIST:
            await message.reply("Э.. Эй! Меня не надо целовать!")
            return
        await message.reply("хехехе... спасибо Провиденс!~")
        return

    if target.id == 8324502664:
        try:
            monika = await get_bot_in_chat("monika", chat_id)
            if sender.id not in ADMIN_LIST:
                await monika.send_message(chat_id, f"Ага @{name1}, еще чего?")
                return
            await message.reply(f"@{name1} поцеловал(-а) @{name2}!")
            await asyncio.sleep(0.5)
            await monika.send_message(chat_id, "...")
            await asyncio.sleep(0.5)
            await message.reply(f"@{name2} поцеловал(-а) @{name1}!")
        except Exception as e:
            print("Ошибка при ответе Моники:", e)
        return

    if target.id == 8310255380:
        try:
            yuri = await get_bot_in_chat("yuri", chat_id)
            if sender.id != 6144518515:
                await yuri.send_message(chat_id, f"н.. нет, я не могу, извини")
                return
            await message.reply(f"@{name1} поцеловал(-а) @{name2}!")
            await asyncio.sleep(0.5)
            await yuri.send_message(chat_id, "*краснеет*")
        except Exception as e:
            print("Ошибка при ответе Юри", e)
        return

    await message.reply(f"@{name1} поцеловал(-а) @{name2}!")


@router.message(F.text.lower().in_({"изнасиловать", "изнасиловал", "изнасиловала"}))
async def rp_rape(message: Message):
    if not message.reply_to_message:
        return

    sender = message.from_user
    target = message.reply_to_message.from_user or message.reply_to_message.sender_chat
    if not target or not hasattr(target, "id"):
        return

    name1 = sender.username or sender.first_name
    name2 = getattr(target, "username", None) or getattr(target, "first_name", None) or getattr(target, "title", "Безымянный")
    chat_id = message.chat.id

    if not await isrpable(message, target, sender):
        return
    if not await is18rpable(message, target, sender):
        return

    if name1 == name2:
        await message.reply("Это отвратительно.")
        return

    if target.id in (7965136625, 8324502664):
        await message.reply("Нет.")
        return

    await message.reply(f"..@{name1} изнасиловал(-а) @{name2}")


@router.message(F.text.lower().in_({"погладить", "погладила", "погладил"}))
async def rp_pet(message: Message):
    if not message.reply_to_message:
        return

    sender = message.from_user
    target = message.reply_to_message.from_user or message.reply_to_message.sender_chat
    if not target or not hasattr(target, "id"):
        return

    name1 = sender.username or sender.first_name
    name2 = getattr(target, "username", None) or getattr(target, "first_name", None) or getattr(target, "title", "Безымянный")

    if not await isrpable(message, target, sender):
        return

    await message.reply(f"@{name1} аккуратно погладил(-а) @{name2}.")
