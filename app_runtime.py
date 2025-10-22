from __future__ import annotations
import asyncio, logging, signal
from fastapi import FastAPI, Request, HTTPException
from aiogram import Bot, Dispatcher, Router, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
import uvicorn

from cfg import (
    bot, TARGET_CHAT_ID, HOST, PORT,
    WEBHOOK_URL, WEBHOOK_PATH, SECRET_TOKEN,
)
from monika.register import register_monika_handlers
from common.utils.db import connect_db
from monika.middlewares.pool import PoolMiddleware

logger = logging.getLogger("monika")

DEBUG = False  # можно менять из “мейнов”

async def send_console_messages(b: Bot):
    import aioconsole
    try:
        while True:
            msg = await aioconsole.ainput("Введите сообщение для отправки в группу: ")
            if msg.strip().lower() in ("exit","quit"): break
            if msg.strip():
                try:    await b.send_message(chat_id=TARGET_CHAT_ID, text=msg)
                except: logger.exception("Не удалось отправить сообщение из консоли")
    except asyncio.CancelledError:
        logger.info("Console task cancelled")

async def build_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())

    if DEBUG:
        dbg = Router()
        @dbg.message()
        async def _dbg_log(m: types.Message):
            logger.debug("INCOMING: user=%s type=%s text=%r",
                         getattr(m.from_user,"id",None), m.content_type, getattr(m,"text",None))
        dp.include_router(dbg)

    register_monika_handlers(dp)
    try:
        pool = await connect_db()
        dp.update.outer_middleware(PoolMiddleware(pool))
        logger.info("DB pool connected and middleware registered")
    except Exception:
        logger.exception("DB connect / middleware registration failed — продолжаем без pool middleware")
    return dp

# ---------- POLLING ----------
async def run_polling():
    dp = await build_dispatcher()
    console_task = asyncio.create_task(send_console_messages(bot))
    polling_task = asyncio.create_task(dp.start_polling(bot))

    def _cancel():
        logger.info("Shutdown signal, cancelling tasks...")
        polling_task.cancel(); console_task.cancel()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try: loop.add_signal_handler(s, _cancel)
        except NotImplementedError: pass

    try:
        await asyncio.gather(polling_task, console_task)
    except asyncio.CancelledError:
        logger.info("Main tasks cancelled")
    finally:
        await bot.session.close()
        try: await dp.storage.close()
        except Exception: pass
        logger.info("Bot stopped (polling)")

# ---------- WEBHOOK ----------
def build_app() -> FastAPI:
    app = FastAPI()
    dp_holder: dict[str, Dispatcher] = {}

    @app.on_event("startup")
    async def on_startup():
        dp = await build_dispatcher()
        dp_holder["dp"] = dp
        await bot.set_webhook(url=WEBHOOK_URL, secret_token=SECRET_TOKEN)
        logger.info("Webhook set to %s", WEBHOOK_URL)

    @app.on_event("shutdown")
    async def on_shutdown():
        await bot.delete_webhook(drop_pending_updates=True)
        await bot.session.close()
        if "dp" in dp_holder:
            try: await dp_holder["dp"].storage.close()
            except Exception: pass
        logger.info("Bot stopped (webhook)")

    @app.get("/health")
    async def health(): return {"ok": True}

    @app.post(WEBHOOK_PATH)
    async def telegram_webhook(request: Request):
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != SECRET_TOKEN:
            raise HTTPException(status_code=403, detail="bad secret")
        update = Update.model_validate(await request.json())
        await dp_holder["dp"].feed_update(bot, update)
        return {"ok": True}

    return app

def run_uvicorn():
    uvicorn.run("app_runtime:build_app", factory=True, host=HOST, port=PORT, reload=True)