from __future__ import annotations
import asyncio, logging, signal
from aiogram import Bot, Dispatcher, Router, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from fastapi import FastAPI, Request, HTTPException
import uvicorn

# локальные импорты
from cfg import (
    bot, TARGET_CHAT_ID,
    WEBHOOK_URL, WEBHOOK_PATH, SECRET_TOKEN,
    HOST, PORT, RUN_MODE
)
from monika.register import register_monika_handlers
from common.db.core import connect_db
from monika.middlewares.pool import PoolMiddleware


# ================= LOGGING =================
DEBUG = RUN_MODE.upper() == "DEBUG"
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("monika.main")


# ================= DISPATCHER =================
async def build_dispatcher() -> Dispatcher:
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Debug router — логирует все входящие апдейты
    if DEBUG:
        dbg = Router()

        @dbg.message()
        async def _dbg_log(m: types.Message):
            logger.debug(
                "INCOMING: user=%s type=%s text=%r",
                getattr(m.from_user, "id", None),
                m.content_type,
                getattr(m, "text", None)
            )
        dp.include_router(dbg)

    # регистрация роутеров проекта
    register_monika_handlers(dp)

    # подключение базы и middleware
    try:
        pool = await connect_db()
        dp.update.outer_middleware(PoolMiddleware(pool))
        logger.info("DB pool connected and middleware registered")
    except Exception:
        logger.exception("DB connect / middleware registration failed — продолжаем без pool middleware")

    return dp


# ================= POLLING MODE =================
async def run_polling():
    dp = await build_dispatcher()

    # очищаем вебхук
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception:
        logger.warning("Не удалось удалить webhook перед polling")

    console_task = asyncio.create_task(_console(bot))
    polling_task = asyncio.create_task(dp.start_polling(bot))

    def _cancel():
        logger.info("Shutdown signal, cancelling tasks...")
        polling_task.cancel()
        console_task.cancel()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _cancel)
        except NotImplementedError:
            pass

    try:
        await asyncio.gather(polling_task, console_task)
    except asyncio.CancelledError:
        logger.info("Main tasks cancelled")
    finally:
        await bot.session.close()
        try:
            await dp.storage.close()
        except Exception:
            pass
        logger.info("Bot stopped (polling)")


async def _console(b: Bot):
    try:
        from aioconsole import ainput  # type: ignore
    except Exception:
        logger.info("aioconsole не установлен — консольная отправка отключена")
        return
    try:
        while True:
            msg = await ainput("Введите сообщение для отправки в группу: ")
            if msg.strip().lower() in ("exit", "quit"):
                break
            if msg.strip():
                try:
                    await b.send_message(chat_id=TARGET_CHAT_ID, text=msg)
                except Exception:
                    logger.exception("Не удалось отправить сообщение из консоли")
    except asyncio.CancelledError:
        logger.info("Console task cancelled")


# ================= WEBHOOK MODE =================
def build_app() -> FastAPI:
    app = FastAPI()
    dp_holder: dict[str, Dispatcher] = {}

    # нормализуем пути
    _path = WEBHOOK_PATH if WEBHOOK_PATH.startswith("/") else "/" + WEBHOOK_PATH
    _path_noslash = _path.rstrip("/")

    @app.on_event("startup")
    async def on_startup():
        dp = await build_dispatcher()
        dp_holder["dp"] = dp
        await bot.set_webhook(url=WEBHOOK_URL, secret_token=SECRET_TOKEN)
        info = await bot.get_webhook_info()
        logger.info("Webhook set: %s", info.url)
        logger.info("Webhook paths mounted: %s and %s", _path, _path_noslash)

    @app.on_event("shutdown")
    async def on_shutdown():
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.session.close()
        if "dp" in dp_holder:
            try:
                await dp_holder["dp"].storage.close()
            except Exception:
                pass
        logger.info("Bot stopped (webhook)")

    @app.get("/health")
    async def health():
        return {"ok": True}

    async def _handle_update(request: Request):
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET_TOKEN:
            raise HTTPException(status_code=403, detail="Bad secret token")
        update = Update.model_validate(await request.json())
        await dp_holder["dp"].feed_update(bot, update)
        return {"ok": True}

    # основной путь
    @app.post(_path)
    async def telegram_webhook(request: Request):
        return await _handle_update(request)

    # алиас без завершающего слэша
    if _path_noslash and _path_noslash != _path:
        @app.post(_path_noslash)
        async def telegram_webhook_alias(request: Request):
            return await _handle_update(request)

    return app


# ================= MAIN ENTRY =================
if __name__ == "__main__":
    mode = RUN_MODE.upper()
    logger.info(f"Starting MonikaBot in {mode} mode")

    if mode == "POLLING":
        asyncio.run(run_polling())
    elif mode == "WEBHOOK":
        uvicorn.run("main:build_app", factory=True, host=HOST, port=int(PORT), reload=False)
    elif mode == "DEBUG":
        asyncio.run(run_polling())
    else:
        raise SystemExit(f"Unknown RUN_MODE: {RUN_MODE!r} (use POLLING / WEBHOOK / DEBUG)")
