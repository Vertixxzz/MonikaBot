from aiogram import F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from common.utils.db import get_user_id_by_username
import redis.asyncio as redis
import random

_redis: redis.Redis | None = None
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

async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    return _redis

def duel_key(chat_id: int, msg_id: int) -> str:
    return f"duel:{chat_id}:{msg_id}"

async def extract_opponent(message: Message, pool) -> int | None:
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id

    parts = message.text.split(maxsplit=2)
    if len(parts) == 3:
        arg = parts[2].lstrip("@")
        if arg.isdigit():
            return int(arg)
        return await get_user_id_by_username(pool, arg, message.chat.id)

    return None

@router.message(F.text.func(lambda t: t and t.lower().startswith("моника дуэль")))
async def duelstart(message: Message, pool):
    r = await get_redis()
    key = duel_key(message.chat.id, message.message_id)

    initiator_id = message.from_user.id
    initiator_username = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name

    opponent_id = await extract_opponent(message, pool)
    if not opponent_id:
        return await message.reply("Не смогла найти соперника. Сделай реплай или укажи @username.")

    opponent_user = message.reply_to_message.from_user if message.reply_to_message else None
    opponent_username = f"@{opponent_user.username}" if (opponent_user and opponent_user.username) else str(opponent_id)

    if initiator_id == opponent_id:
        return await message.reply("Нельзя дуэлиться с самим собой!")

    await r.hset(key, mapping={
        "initiator_id": initiator_id,
        "initiator_username": initiator_username,
        "opponent_id": opponent_id,
        "opponent_username": opponent_username,
        "status": "pending",
        "turn": initiator_id
    })
    await r.expire(key, 3600)  # жить 1 час

    await message.reply(
        f"{initiator_username} вызывает {opponent_username} на дуэль!\nПримешь?",
        reply_markup=accept
    )

@router.callback_query(F.data == "dueldeny")
async def on_deny(cb: CallbackQuery):
    r = await get_redis()
    key = duel_key(cb.message.chat.id, cb.message.message_id)
    duel_data = await r.hgetall(key)

    if not duel_data:
        return await cb.answer("Дуэль уже неактивна")

    if cb.from_user.id != int(duel_data["opponent_id"]):
        return await cb.answer("Эта кнопка не для тебя!", show_alert=True)

    await cb.answer("Дуэль отклонена")
    await cb.message.edit_text("Противник отклонил дуэль.")
    await r.delete(key)

@router.callback_query(F.data == "duelaccept")
async def on_accept(cb: CallbackQuery):
    r = await get_redis()
    key = duel_key(cb.message.chat.id, cb.message.message_id)
    duel_data = await r.hgetall(key)

    if not duel_data:
        return await cb.answer("Дуэль уже неактивна")

    if cb.from_user.id != int(duel_data["opponent_id"]):
        return await cb.answer("Эта кнопка не для тебя!", show_alert=True)

    await r.hset(key, "status", "active")
    await cb.answer("Дуэль принята!")

    await cb.message.edit_text(
        "Дуэль началась!\n\n"
        "На каждый выстрел будет выделено по 1 минуте\n\n"
        f"Первым стреляет {duel_data['initiator_username']}",
        reply_markup=duel
    )

@router.callback_query(F.data == "shot")
async def on_shot(cb: CallbackQuery):
    r = await get_redis()
    key = duel_key(cb.message.chat.id, cb.message.message_id)
    duel_data = await r.hgetall(key)

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

    if random.random() < 0.1:
        await cb.message.edit_text(
            f"{cb.from_user.full_name} попал!\nПобеда!",
            reply_markup=None
        )
        await r.delete(key)
    else:
        next_turn = opponent_id if allowed_id == initiator_id else initiator_id
        next_username = duel_data["opponent_username"] if next_turn == opponent_id else duel_data["initiator_username"]

        await r.hset(key, "turn", next_turn)
        await cb.answer("Мимо!")
        await cb.message.edit_text(
            f"{cb.from_user.full_name} промахнулся!\nТеперь ход за {next_username}",
            reply_markup=duel
        )


