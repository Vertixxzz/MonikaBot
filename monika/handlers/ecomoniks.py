from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from common.db.economics import (
    add_wallet, get_balance, add_balance, transfer_money
)
import random
from datetime import datetime, timedelta, timezone
from cfg import ADMIN_LIST

BASE_AMOUNT = 200
COOLDOWN = timedelta(hours=2)
ACCUM_DURATION = timedelta(hours=4)
RATE_PER_HOUR = 100
MAX_AMOUNT = BASE_AMOUNT + int(ACCUM_DURATION.total_seconds() / 3600) * RATE_PER_HOUR

router = Router()
early_reply = ["Успеется, хапуга.", "Терпение - добродетель.", "Я только недавно давала тебе денег!","иди нахуй"]

def _compute_claim(elapsed: timedelta) -> tuple[bool, int, timedelta]:
    if elapsed < COOLDOWN:
        return False, 0, (COOLDOWN - elapsed)

    after = elapsed - COOLDOWN
    capped_after = min(after, ACCUM_DURATION)

    hours = capped_after.total_seconds() / 3600.0
    amount = BASE_AMOUNT + int(hours * RATE_PER_HOUR)

    if amount > MAX_AMOUNT:
        amount = MAX_AMOUNT

    return True, amount, timedelta(0)

def to_utc_naive(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)

@router.message((F.text.casefold().in_(["моника дай денег", "дай денег"])))
async def monika_claim_money(message: Message, pool):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.full_name

    await add_wallet(pool, user_id, username)

    if user_id in ADMIN_LIST:
        amount = random.randint(25, 75)
        await add_balance(pool, user_id, username, amount)
        await message.reply(f"Держи легенда @{username}, вот тебе {amount} докидолларов!")
        return

    now = datetime.now(timezone.utc)

    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                SELECT balance, last_claim_at
                FROM wallets
                WHERE user_id = $1
                FOR UPDATE
                """,
                user_id,
            )

            last_claim_at = row["last_claim_at"] if row else None

            if last_claim_at is None:
                amount = BASE_AMOUNT
                await conn.execute(
                    "UPDATE wallets SET last_claim_at = now() WHERE user_id = $1",
                    user_id,
                )
                await add_balance(pool, user_id, username, amount)
                await message.reply(f"Держи, вот тебе {amount} докидолларов!")
                return

            if last_claim_at.tzinfo is None:
                last_claim_at = last_claim_at.replace(tzinfo=timezone.utc)

            elapsed = now - last_claim_at
            available, amount, remaining = _compute_claim(elapsed)

            if not available:
                minutes = int(remaining.total_seconds() // 60)
                seconds = int(remaining.total_seconds() % 60)
                await message.reply(
                    random.choice(early_reply)
                    + f"\nПопробуй снова через {minutes} мин. и {seconds} сек."
                )
                return

            await conn.execute(
                "UPDATE wallets SET last_claim_at = now() WHERE user_id = $1",
                user_id,
            )
    await add_balance(pool, user_id, username, amount)
    await message.reply(f"Держи, вот тебе {amount} докидолларов!")


@router.message((F.text.casefold().in_(["моника баланс", "баланс"])))
async def check_balance(message: Message, pool):
    user_id = message.from_user.id
    balance = await get_balance(pool, user_id)

    if balance <= 0:
        await message.reply("У тебя нулевоЙ баланс")
    else:
        await message.reply(f"У тебя на счету {balance} докидолларов")


@router.message(F.text.lower().startswith("дать"))
async def give_money_handler(message: Message, pool):
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        return await message.reply("Укажи сумму: например, 'дать 25'")

    amount = int(parts[1])
    if amount <= 0:
        return await message.reply("Сумма должна быть положительной.")

    if not message.reply_to_message or not message.reply_to_message.from_user:
        return await message.reply("Ответь на сообщение пользователя, которому хочешь передать деньги.")

    sender_id = message.from_user.id
    receiver = message.reply_to_message.from_user
    receiver_id = receiver.id
    username_rec = receiver.username or receiver.full_name

    if sender_id == receiver_id:
        return await message.reply("Нельзя перевести деньги самому себе")

    try:
        await transfer_money(pool, sender_id, receiver_id, username_rec, amount)
        await message.reply(f"Передала @{username_rec} {amount} докидолларов")
    except ValueError as e:
        msg = str(e)
        if msg == "У отправителя нет кошелька":
            await message.reply("У тебя ещё нет кошелька! Сначала попроси у Меня немного денег.")
        elif msg == "Недостаточно средств":
            await message.reply("Недостаточно средств")
        else:
            await message.reply("Что-то пошло не так...")
