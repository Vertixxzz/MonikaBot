from aiogram import Router, F, types
import random
from common.db.economics import add_balance,get_balance
from common.db.beer import drink_beer, get_beer

router = Router()

@router.message(F.text.casefold() == "моника дай пиво")
async def handle_give_beer(message: types.Message, pool):
    user = message.from_user
    user_id = user.id
    chat_id = message.chat.id
    username = user.username or user.full_name or f"id{user_id}"

    price = 100
    beer_amount = round(random.uniform(1.0, 5.0), 2)

    money = await get_balance(pool, user_id, chat_id)   # <-- добавили chat_id
    if money < price:
        await message.reply("У тебя недостаточно средств!")
        return

    try:
        await add_balance(pool, user_id, chat_id, username, -price)  # <-- chat_id
        await drink_beer(pool, user_id, chat_id, beer_amount)
        await message.reply(f"Налила {beer_amount} пива. Приятного!")
    except Exception as e:
        print("ошибка в наливании", repr(e))
        await message.reply("не пьется друг. не пьется")

@router.message(F.text.lower() == "моника пиво стата")
async def check_beer(message: types.Message, pool):
    user = message.from_user
    user_id = user.id
    chat_id = message.chat.id
    amount = await get_beer(pool, user_id, chat_id)
    if amount is None or amount == 0:
        await message.reply("В тебе ни миллилитра пива")
        return
    amount = round(amount, 2)
    await message.reply(f"Ты выпил {amount} пива")