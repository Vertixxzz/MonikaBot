from aiogram import Router, F
from aiogram.types import Message
from common.db.economics import (
    add_wallet, get_balance, add_balance, transfer_money
)
import random
from datetime import datetime, timedelta, timezone
from cfg import ADMIN_LIST

router = Router()
early_reply = ["Успеется, хапуга.", "Терпение — добродетель.", "Я только недавно давала тебе денег!"]

def to_utc_naive(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


@router.message(F.text.lower() == "моника дай денег")
async def monika_claim_money(message: Message, pool):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.full_name
    chat_id = message.chat.id

    # создаём кошелёк, если его нет
    await add_wallet(pool, user_id, chat_id, username)

    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT balance, updated_at
            FROM wallets
            WHERE user_id = $1 AND chat_id = $2
        """, user_id, chat_id)

    if user_id in ADMIN_LIST:
        amount = random.randint(25, 75)
        await add_balance(pool, user_id, chat_id, username, amount)
        await message.reply(f"Держи вертикс моя любовь, вот тебе {amount} докидолларов!")
        return

    now = datetime.utcnow()
    if row and row["updated_at"]:
        last = to_utc_naive(row["updated_at"])
        delta = now - last
        if delta < timedelta(hours=1):
            remaining = timedelta(hours=1) - delta
            minutes = int(remaining.total_seconds() // 60)
            seconds = int(remaining.total_seconds() % 60)
            await message.reply(
                f"Пока рано! Попробуй снова через {minutes} минут и {seconds} секунд"
            )
            return

    # выдаём деньги
    amount = random.randint(25, 75)
    await add_balance(pool, user_id, chat_id, username, amount)
    await message.reply(f"Держи, вот тебе {amount} докидолларов!")

@router.message(F.text.lower().startswith("моника баланс"))
async def check_balance(message: Message, pool):
    user_id = message.from_user.id
    chat_id = message.chat.id
    balance = await get_balance(pool, user_id, chat_id)
    if balance is None or balance <= 0:
        await message.reply("У тебя нету денег")
        return
    else:
        await message.reply(f"У тебя на счету {balance} докидолларов!")

@router.message(F.text.lower().startswith("дать"))
async def give_money_handler(message: Message, pool):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await message.reply("Укажи сумму: например, 'дать 25'")

    amount = int(parts[1])
    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply("Ответь на сообщение пользователя, которому хочешь передать деньги.")

    sender_id = message.from_user.id
    receiver_id = message.reply_to_message.from_user.id
    username_rec = message.reply_to_message.from_user.username or message.reply_to_message.from_user.full_name
    chat_id = message.chat.id

    try:
        await transfer_money(pool, sender_id, receiver_id, chat_id, username_rec, amount)
        await message.reply(f"Передала {username_rec} {amount} докидолларов 💸")
    except ValueError as e:
        if str(e) == "no_sender_wallet":
            await message.reply("У тебя ещё нет кошелька! Получи немного денег сначала.")
        elif str(e) == "not_enough_money":
            await message.reply("Недостаточно средств.")
        else:
            await message.reply("Что-то пошло не так...")
