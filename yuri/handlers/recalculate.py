import logging
from aiogram import Router, types, F

from common.db.cardrec import recalculate_cards_for_chat
from common.db.presence import sync_presence_for_chat

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text.func(lambda t: t and t.lower().startswith("юри пересчет")))
async def recalculate_cards(message: types.Message, pool):
    if message.from_user.id != 8022353456:
        await message.answer("Я.. я не думаю, что тебе стоит этим заниматься..")
        return

    chat_id = message.chat.id

    await message.answer(
        "Хорошо..\n"
        "дай мне немного времени\n"
        "_я считаю.._"
    )

    try:
        stats = await sync_presence_for_chat(
            bot=message.bot,
            pool=pool,
            chat_id=chat_id,
            per_request_delay=0.05,
        )

        async with pool.acquire() as conn:
            async with conn.transaction():
                count = await recalculate_cards_for_chat(conn, chat_id)

    except Exception:
        logger.exception("Error during Yuri recalculation")
        await message.answer(
            "Ох..\n"
            "что-то пошло не так во время пересчёта.."
        )
        return

    if count == 0:
        await message.answer(
            "Хм..\n"
            "я не нашла ни одного участника с сообщениями..\n"
            "похоже, считать пока нечего"
        )
        return

    await message.answer(
        "Готово..!\n"
        f"Проверено: `{stats.total}`\n"
        f"В чате: `{stats.set_true}`\n"
        f"Не в чате: `{stats.set_false}`\n"
        f"Пропущено (ошибки): `{stats.skipped_errors}`\n\n"
        f"Я обновила карточки для `{count}` участников этого чата"
    )

