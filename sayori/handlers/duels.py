from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from common.db.utilities import get_user_id_by_username
from common.db.economics import add_balance
from common.db.duels import create_duel, get_duel, delete_duel, set_status, set_turn
import random

router = Router()

accept = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Принять", callback_data="duelaccept")],
        [InlineKeyboardButton(text="Отказать", callback_data="dueldeny")],
    ]
)

duel = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Выстрел", callback_data="shot")],
        [InlineKeyboardButton(text="Сдаться", callback_data="surrender")],
    ]
)


def _duel_pk(cb_or_msg):
    chat_id = cb_or_msg.message.chat.id if isinstance(cb_or_msg, CallbackQuery) else cb_or_msg.chat.id
    msg_id = cb_or_msg.message.message_id if isinstance(cb_or_msg, CallbackQuery) else cb_or_msg.message_id
    return chat_id, msg_id


async def extract_opponent(message: Message, pool) -> int | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id

    parts = (message.text or "").split(maxsplit=2)
    if len(parts) == 3:
        arg = parts[2].lstrip("@")
        if arg.isdigit():
            return int(arg)
        return await get_user_id_by_username(pool, arg)
    return None


@router.message(F.text.func(lambda t: t and t.lower().startswith("сайори дуэль")))
async def duel_start(message: Message, pool):
    chat_id = message.chat.id

    initiator_id = message.from_user.id
    initiator_username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name

    opponent_id = await extract_opponent(message, pool)
    if not opponent_id:
        return await message.reply("Я не нашла, с кем ты хочешь сразиться. Сделай реплай или укажи @username")

    if initiator_id == opponent_id:
        return await message.reply("Эм… с собой дуэль? Это даже я бы выиграла!!")

    opponent_user = message.reply_to_message.from_user if message.reply_to_message else None
    opponent_username = (
        f"@{opponent_user.username}" if (opponent_user and opponent_user.username)
        else (f"@{message.entities[2].text.lstrip('@')}" if message.entities and len(message.entities) >= 3 else str(opponent_id))
    )

    sent = await message.reply(
        f"{initiator_username} вызывает {opponent_username} на дуэль!\n"
        f"Смело, смело... принимаешь вызов?",
        reply_markup=accept,
    )

    await create_duel(
        pool,
        chat_id=chat_id,
        message_id=sent.message_id,
        initiator_id=initiator_id,
        initiator_username=initiator_username,
        opponent_id=opponent_id,
        opponent_username=opponent_username,
        ttl_seconds=3600,
    )


@router.callback_query(F.data == "dueldeny")
async def on_deny(cb: CallbackQuery, pool):
    chat_id, msg_id = _duel_pk(cb)
    duel_data = await get_duel(pool, chat_id, msg_id)
    if not duel_data:
        return await cb.answer("Дуэль уже неактивна")

    if cb.from_user.id != int(duel_data["opponent_id"]):
        return await cb.answer("Эта кнопка не для тебя!", show_alert=True)

    await cb.answer("Дуэль отклонена")
    await cb.message.edit_text("Противник отказался от дуэли. Может, в другой раз?")
    await delete_duel(pool, chat_id, msg_id)


@router.callback_query(F.data == "duelaccept")
async def on_accept(cb: CallbackQuery, pool):
    chat_id, msg_id = _duel_pk(cb)
    duel_data = await get_duel(pool, chat_id, msg_id)
    if not duel_data:
        return await cb.answer("Дуэль уже неактивна")

    if cb.from_user.id != int(duel_data["opponent_id"]):
        return await cb.answer("Эта кнопка не для тебя!", show_alert=True)

    await set_status(pool, chat_id, msg_id, "active")
    await cb.answer("Дуэль принята!")

    await cb.message.edit_text(
        "Дуэль началась!\n\n"
        "На каждый выстрел даётся минута.\n"
        f"Первым стреляет {duel_data['initiator_username']}",
        reply_markup=duel,
    )


@router.callback_query(F.data == "shot")
async def on_shot(cb: CallbackQuery, pool):
    chat_id, msg_id = _duel_pk(cb)
    duel_data = await get_duel(pool, chat_id, msg_id)

    if not duel_data or duel_data.get("status") != "active":
        return await cb.answer("Дуэль не активна")

    shooter_id = cb.from_user.id
    allowed_id = int(duel_data["turn"])
    initiator_id = int(duel_data["initiator_id"])
    opponent_id = int(duel_data["opponent_id"])

    if shooter_id not in (initiator_id, opponent_id):
        return await cb.answer("Ты не участник дуэли!", show_alert=True)

    if shooter_id != allowed_id:
        return await cb.answer("Сейчас не твой ход!", show_alert=True)

    if random.random() < 0.05:
        await cb.message.edit_text(
            f"{cb.from_user.full_name} попал!\n Победа!",
            reply_markup=None,
        )

        user = cb.from_user
        await add_balance(pool, user.id, user.username or user.first_name, 25)
        await cb.message.answer(f"{user.first_name} получает +25 докидолларов! ")

        await delete_duel(pool, chat_id, msg_id)
    else:
        next_turn = opponent_id if allowed_id == initiator_id else initiator_id
        next_username = duel_data["opponent_username"] if next_turn == opponent_id else duel_data["initiator_username"]

        await set_turn(pool, chat_id, msg_id, next_turn)
        await cb.answer("Мимо!")
        await cb.message.edit_text(
            f"Выстрел @{cb.from_user.full_name} не попадает! !\nТеперь ход за @{next_username}",
            reply_markup=duel,
        )


@router.callback_query(F.data == "surrender")
async def on_surrender(cb: CallbackQuery, pool):
    chat_id, msg_id = _duel_pk(cb)
    duel_data = await get_duel(pool, chat_id, msg_id)
    if not duel_data or duel_data.get("status") != "active":
        return await cb.answer("Дуэль не активна")

    who = cb.from_user.id
    initiator_id = int(duel_data["initiator_id"])
    opponent_id = int(duel_data["opponent_id"])

    if who not in (initiator_id, opponent_id):
        return await cb.answer("Ты не участник дуэли!", show_alert=True)

    winner_name = duel_data["opponent_username"] if who == initiator_id else duel_data["initiator_username"]
    await cb.message.edit_text(f"{cb.from_user.full_name} сдается.\nПобеждает {winner_name}!", reply_markup=None)
    await delete_duel(pool, chat_id, msg_id)