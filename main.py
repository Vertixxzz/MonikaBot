import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage

import aioconsole

from cfg import bot, TARGET_CHAT_ID
from monika.register import register_monika_handlers
from common.utils.db import connect_db
from monika.middlewares.pool import PoolMiddleware

DEBUG = False

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("monika.main")


async def send_console_messages(bot: Bot):
    try:
        while True:
            message = await aioconsole.ainput("Введите сообщение для отправки в группу: ")
            if message.strip().lower() in ("exit", "quit"):
                logger.info("Выход из режима консоли.")
                break
            if not message.strip():
                continue
            try:
                await bot.send_message(chat_id=TARGET_CHAT_ID, text=message)
            except Exception:
                logger.exception("Не удалось отправить сообщение из консоли")
    except asyncio.CancelledError:
        logger.info("Console task cancelled")


async def main():
    globals()["monika_bot"] = bot

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # DEBUG router - логирует все приходящие сообщения, помогает понять, доходят ли апдейты
    if DEBUG:
        debug_router = Router()

        @debug_router.message()
        async def _debug_log(message: Message):
            logger.debug(
                "INCOMING: user=%s type=%s text=%r",
                getattr(message.from_user, "id", None),
                message.content_type,
                getattr(message, "text", None),
            )

        dp.include_router(debug_router)

    # Регистрируем роутеры из проекта
    register_monika_handlers(dp)

    # Подключаем базу данных и регаем middleware безопасно
    pool = None
    try:
        pool = await connect_db()
        # Регистрируем middleware — это может бросить исключение, поэтому в try
        dp.update.outer_middleware(PoolMiddleware(pool))
        logger.info("DB pool connected and middleware registered")
    except Exception:
        logger.exception("DB connect / middleware registration failed — продолжаем без pool middleware")

    # Запускаем две задачи: polling и консоль
    console_task = asyncio.create_task(send_console_messages(bot))
    polling_task = asyncio.create_task(dp.start_polling(bot))

    # Обработчики сигналов (SIGINT/SIGTERM) для graceful shutdown
    def _cancel_tasks():
        logger.info("Got shutdown signal, cancelling tasks...")
        polling_task.cancel()
        console_task.cancel()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _cancel_tasks)
        except NotImplementedError:
            pass

    try:
        await asyncio.gather(polling_task, console_task)
    except asyncio.CancelledError:
        logger.info("Main tasks cancelled, shutting down")
    finally:
        try:
            await bot.session.close()
        except Exception:
            logger.exception("Ошибка при закрытии bot.session")

        if pool:
            try:
                await pool.close()
            except Exception:
                logger.exception("Ошибка при закрытии pool")

        try:
            await storage.close()
        except Exception:
            logger.exception("Ошибка при закрытии storage")

        logger.info("Bot stopped")


if __name__ == "__main__":
    asyncio.run(main())
