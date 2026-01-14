from aiogram import Router, F
from aiogram.types import Message
from common.db.promocode import activate_promo

router = Router()


@router.message(F.text.lower().startswith("моника промо"))
async def handle_promo(message: Message, pool):
    args = message.text.split(maxsplit=2)

    if len(args) < 3 or not args[2].strip():
        return await message.reply(
            "Введи промокод, например: `моника промо <промокод>`"
        )

    promo_code = args[2].strip()
    user_id = message.from_user.id

    try:
        reward = await activate_promo(pool, user_id, promo_code)
        await message.reply(f"Промокод активирован! Перевела на твой кошелек {reward} докидолларов")

    except ValueError as e:
        msg = str(e)
        if msg == "invalid_code":
            await message.reply("Такого промокода нет или он уже не активен")
        elif msg == "already_used":
            await message.reply("Ты уже использовал этот промокод")
        elif msg == "limit_reached":
            await message.reply("Промокод больше недоступен - лимит активаций достигнут")
        else:
            await message.reply("Что-то пошло не так... попробуй чуть позже")

