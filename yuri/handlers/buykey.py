from aiogram import Router, types, F
from common.db.lootboxes import add_key
from common.db.economics import get_balance, add_balance

router = Router()

@router.message(F.text.func(lambda t: t and t.lower().startswith("продай ключ")))
async def buykey(message: types.Message, Pool):
    balance = await get_balance(Pool, message.from_user.id)
    if balance < 1000:
        await message.reply(f"Я боюсь.. что тебе не хватает докидолларов. Один ключ стоит 1000, у тебя сейчас {balance}")
        return
    await add_balance(Pool, message.from_user.id, message.from_user.username, -1000)
    await add_key(Pool, message.from_user.id, message.chat.id)

    await message.reply("Готово! Я добавила тебе один ключ!")


