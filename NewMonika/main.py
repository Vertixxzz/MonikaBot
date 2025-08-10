# main_fixed.py
"""
Переписанный main для NewMonika.
Цель: убрать типичные косяки с регистрацией роутеров, middleware и shutdown,
помочь дебажить (debug router) и аккуратно закрывать ресурсы.

Как пользоваться:
- Заменяй этот файл вместо старого main.py (или сохраняй рядом и запускай).
- Для отладки установи DEBUG = True (по умолчанию True).
- В handler'ах лучше принимать bot через DI: async def handler(message: Message, bot: Bot)
  или импортировать объект monika_bot из этого модуля (см. globals()["monika_bot"]).

Не менял ваш register_monika_handlers/модули — они должны оставаться такими же.
Если у тебя есть циклические импорты — лучше поправить хэндлеры, чтобы бот приходил через параметр.
"""

import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.fsm.storage.memory import MemoryStorage

import aioconsole

# локальные импорты проекта
from cfg import MONIKATOKEN, TARGET_CHAT_ID
from monika.register import register_monika_handlers
from NewMonika.common.utils.db import connect_db
from monika.middlewares.pool import PoolMiddleware

# Включи DEBUG на время отладки — потом можешь выключить
DEBUG = True

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("monika.main")


async def send_console_messages(bot: Bot):
    """Асинхронная консоль для отправки сообщений в группу.
    Можно отключить просто не запуская таск или поставив DEBUG=False.
    """
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
    # Создаём объект бота
    bot = Bot(token=MONIKATOKEN)

    # Экспорт объекта бота в глобальную область имен — если в твоих хэндлерах
    # кто-то делает "from main_fixed import monika_bot as bot" — это работает.
    # Но лучше использовать DI (handler(..., bot: Bot)).
    globals()["monika_bot"] = bot

    # Диспетчер с in-memory storage. MemoryStorage подходит для большинства случаев.
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # DEBUG router — логирует все приходящие сообщения, помогает понять, доходят ли апдейты
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
            # На windows loop.add_signal_handler может быть не реализован
            pass

    try:
        await asyncio.gather(polling_task, console_task)
    except asyncio.CancelledError:
        logger.info("Main tasks cancelled, shutting down")
    finally:
        # Cleanup resources
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
