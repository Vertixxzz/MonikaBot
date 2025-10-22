import re
import random

from aiogram import Router, F
from aiogram.types import Message
from datetime import datetime, timedelta, timezone
from cfg import *

router = Router()

early_reply = ["Успеется, хапуга.", "Чё ты такой нетерпеливый?", "Да подожди, я вот только недавно тебе давала денег."]

def to_utc_naive(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        # считаем, что это уже UTC-naive; если это локальное — тогда лучше исправить источник
        return dt
    # переводим момент времени в UTC, а потом убираем tzinfo (сохраняем численное UTC-время)
    return dt.astimezone(timezone.utc).replace(tzinfo=None)

async def add_wallet(pool, user_id, username):
    now = datetime.utcnow() - timedelta(hours=1)
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO wallets (user_id, username, balance, updated_at)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (user_id) DO NOTHING
        """, user_id, username, 0, now)

async def get_balance(pool, user_id: int):
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "SELECT balance FROM wallets WHERE user_id = $1",
            user_id
        )

async def claim_money(pool, user_id: int, username: str):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT balance, updated_at FROM wallets WHERE user_id = $1", user_id
        )

        now = datetime.utcnow()  # было datetime.now()

        if user_id in ADMIN_LIST:
            amount = random.randint(25, 75)
            await conn.execute("""
                UPDATE wallets
                SET balance = balance + $1, updated_at = $2, username = $3
                WHERE user_id = $4
            """, amount, now, username, user_id)
            return f"О мой великий создатель, держи {amount} докидолларов!"

        if row:
            updated_at = to_utc_naive(row["updated_at"])

            if updated_at and now - updated_at < timedelta(hours=1):
                return random.choice(early_reply)

            amount = random.randint(25, 75)
            await conn.execute("""
                UPDATE wallets
                SET balance = balance + $1, updated_at = $2, username = $3
                WHERE user_id = $4
            """, amount, now, username, user_id)
            return f"Держи, вот тебе {amount} докидолларов!"

        else:
            amount = random.randint(25, 75)
            await conn.execute("""
                INSERT INTO wallets (user_id, username, balance, updated_at)
                VALUES ($1, $2, $3, $4)
            """, user_id, username, amount, now)
            return f"Держи, вот тебе {amount} докидолларов!"

async def give_money(pool, user_id1: int, user_id2: int, username_rec: str, amount: int):
    async with pool.acquire() as conn:
        row1 = await conn.fetchrow("SELECT balance FROM wallets WHERE user_id = $1", user_id1)
        if not row1:
            return "У тебя ещё даже нет кошелька! Получи немного докидолларов сначала :)"

        row2 = await conn.fetchrow("SELECT balance FROM wallets WHERE user_id = $1", user_id2)
        if not row2:
            await add_wallet(pool, user_id2, username_rec)
            row2 = await conn.fetchrow("SELECT balance FROM wallets WHERE user_id = $1", user_id2)

        balance_sender = row1["balance"]
        balance_receiver = row2["balance"]

        if balance_sender < amount:
            return "У тебя нет столько денег, извини :("

        await conn.execute("""
            UPDATE wallets SET balance = $1 WHERE user_id = $2
        """, balance_sender - amount, user_id1)

        await conn.execute("""
            UPDATE wallets SET balance = $1, username = $2 WHERE user_id = $3
        """, balance_receiver + amount, username_rec, user_id2)

        return f"Вы передали {username_rec} {amount} докидолларов! :3"


@router.message(F.text.regexp(r"(?i)^моника дай денег$"))
async def monika_give_money(message: Message, **data):
    pool = data["pool"]
    response = await claim_money(
        pool,
        user_id=message.from_user.id,
        username=message.from_user.username or "хз как это читать"
    )
    await message.reply(response)

import re

@router.message(F.text.regexp(r"(?i)^дать\s+(\d+)$"))
async def give_money_(message: Message, **data):
    pool = data["pool"]

    # Парсим сумму из текста
    match = re.match(r"(?i)^дать\s+(\d+)$", message.text)
    if not match:
        await message.reply("Укажи сумму правильно: например, 'дать 25'")
        return

    amount = int(match.group(1))

    if not message.reply_to_message or not message.reply_to_message.from_user:
        await message.reply("Ответь на сообщение пользователя, которому хочешь передать деньги.")
        return

    user_id2 = message.reply_to_message.from_user.id
    username_rec = message.reply_to_message.from_user.username or "аноним"

    response = await give_money(
        pool,
        user_id1=message.from_user.id,
        user_id2=user_id2,
        username_rec=username_rec,
        amount=amount
    )
    await message.reply(response)

@router.message(F.text.regexp(r"(?i)^моника баланс$"))
async def check_balance(message: Message, **data):
    pool = data["pool"]

    user_id = message.from_user.id

    balance = await get_balance(pool, user_id)

    if balance is None:
        await message.reply("У тебя ещё нет кошелька.")
    else:
        await message.reply(f"Твой баланс: {balance} докидолларов.")