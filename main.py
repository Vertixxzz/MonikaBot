from __future__ import annotations
import asyncio, logging, signal
from aiogram import Bot, Dispatcher, Router, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update
from fastapi import FastAPI, Request, HTTPException
from common.utils.links import register_bot
import uvicorn

#локалка
from cfg import (
    HOST, PORT, RUN_MODE, TARGET_CHAT_ID,
    MONIKATOKEN, SAYORITOKEN,
    BASE_URL,
    WEBHOOK_PATH_MONIKA, WEBHOOK_PATH_SAYORI,
    SECRET_TOKEN_MONIKA, SECRET_TOKEN_SAYORI,
)
from monika.monika_register import register_monika_handlers, register_monika_middlewares
from sayori.sayori_register import register_sayori_handlers, register_sayori_middlewares
from common.db.core import connect_db
from monika.middlewares.pool import PoolMiddleware

# ================= LOGGING =================
DEBUG = RUN_MODE.upper() == "DEBUG"
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("multibot.main")


# ================= BUILD DISPATCHERS =================
async def build_dispatchers():
    """
    Создаёт два Bot/Dispatcher, общий pool, вешает middlewares/handlers.
    Возвращает: (monika_bot, monika_dp, sayori_bot, sayori_dp)
    """
    monika_bot = Bot(token=MONIKATOKEN)
    sayori_bot = Bot(token=SAYORITOKEN)

    monika_dp = Dispatcher(storage=MemoryStorage())
    sayori_dp = Dispatcher(storage=MemoryStorage())

    if DEBUG:
        def add_debug_router(dp: Dispatcher):
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

        add_debug_router(monika_dp)
        add_debug_router(sayori_dp)

    pool = await connect_db()

    # --- Monika ---
    register_monika_middlewares(monika_dp, pool)
    monika_dp.update.outer_middleware(PoolMiddleware(pool))
    register_monika_handlers(monika_dp)


    # --- Sayori ---
    register_sayori_middlewares(sayori_dp)
    sayori_dp.update.outer_middleware(PoolMiddleware(pool))
    register_sayori_handlers(sayori_dp)

    register_bot("monika", monika_bot)
    register_bot("sayori", sayori_bot)

    logger.info("Dispatchers ready: Monika & Sayori")
    return monika_bot, monika_dp, sayori_bot, sayori_dp


# ================= POLLING =================
async def build_polling_side():
    """
    Билдер для режима polling: чистит вебхуки у ОБОИХ ботов,
    чтобы не было конфликтов, и возвращает объекты.
    """
    monika_bot, monika_dp, sayori_bot, sayori_dp = await build_dispatchers()
    # удаляем вебхуки у обоих
    for bot, name in ((monika_bot, "monika"), (sayori_bot, "sayori")):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted for %s (polling mode)", name)
        except Exception:
            logger.warning("Не удалось удалить webhook перед polling (%s)", name)
    return monika_bot, monika_dp, sayori_bot, sayori_dp


async def _console(bot: Bot, label: str):
    """Простейшая консольная отправка в TARGET_CHAT_ID (опционально)."""
    try:
        from aioconsole import ainput  # type: ignore
    except Exception:
        logger.info("aioconsole не установлен — консольная отправка отключена")
        return
    try:
        while True:
            msg = await ainput(f"[{label}] message> ")
            if msg.strip().lower() in ("exit", "quit"):
                break
            if msg.strip():
                try:
                    await bot.send_message(chat_id=TARGET_CHAT_ID, text=f"[{label}] {msg}")
                except Exception:
                    logger.exception("Не удалось отправить сообщение из консоли")
    except asyncio.CancelledError:
        logger.info("Console task cancelled (%s)", label)


async def run_polling_both():
    """
    Параллельный polling для Monika и Sayori.
    Корректно ловит SIGINT/SIGTERM и завершает обе задачи.
    """
    monika_bot, monika_dp, sayori_bot, sayori_dp = await build_polling_side()

    tasks = [
        asyncio.create_task(monika_dp.start_polling(monika_bot), name="monika_polling"),
        asyncio.create_task(sayori_dp.start_polling(sayori_bot), name="sayori_polling"),
        asyncio.create_task(_console(monika_bot, "Monika"), name="monika_console"),
        asyncio.create_task(_console(sayori_bot, "Sayori"), name="sayori_console"),
    ]

    def _cancel_all():
        logger.info("Shutdown signal, cancelling tasks...")
        for t in tasks:
            t.cancel()

    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(s, _cancel_all)
        except NotImplementedError:
            pass

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Polling tasks cancelled")
    finally:
        for bot, dp, name in (
            (monika_bot, monika_dp, "monika"),
            (sayori_bot, sayori_dp, "sayori"),
        ):
            try:
                await bot.session.close()
            except Exception:
                logger.exception("Bot session close failed (%s)", name)
            try:
                await dp.storage.close()
            except Exception:
                logger.exception("DP storage close failed (%s)", name)
        logger.info("Both bots stopped (polling)")


# ================= WEBHOOK APP =================
def build_app() -> FastAPI:
    app = FastAPI()

    holder: dict[str, object] = {}

    path_monika = WEBHOOK_PATH_MONIKA if WEBHOOK_PATH_MONIKA.startswith("/") else "/" + WEBHOOK_PATH_MONIKA
    path_sayori = WEBHOOK_PATH_SAYORI if WEBHOOK_PATH_SAYORI.startswith("/") else "/" + WEBHOOK_PATH_SAYORI

    @app.on_event("startup")
    async def on_startup():
        monika_bot, monika_dp, sayori_bot, sayori_dp = await build_dispatchers()
        holder["monika_bot"] = monika_bot
        holder["monika_dp"] = monika_dp
        holder["sayori_bot"] = sayori_bot
        holder["sayori_dp"] = sayori_dp

        await monika_bot.delete_webhook(drop_pending_updates=True)
        await sayori_bot.delete_webhook(drop_pending_updates=True)

        await monika_bot.set_webhook(f"{BASE_URL}{path_monika}", secret_token=SECRET_TOKEN_MONIKA)
        await sayori_bot.set_webhook(f"{BASE_URL}{path_sayori}", secret_token=SECRET_TOKEN_SAYORI)

        mi = await monika_bot.get_webhook_info()
        si = await sayori_bot.get_webhook_info()
        logger.info("Monika webhook: %s", mi.url)
        logger.info("Sayori webhook: %s", si.url)

    @app.on_event("shutdown")
    async def on_shutdown():
        for key in ("monika_bot", "sayori_bot"):
            bot_obj: Bot = holder.get(key)  # type: ignore
            if bot_obj:
                try:
                    await bot_obj.delete_webhook(drop_pending_updates=True)
                except Exception:
                    pass
                try:
                    await bot_obj.session.close()
                except Exception:
                    pass
        for key in ("monika_dp", "sayori_dp"):
            dp_obj: Dispatcher = holder.get(key)  # type: ignore
            if dp_obj:
                try:
                    await dp_obj.storage.close()
                except Exception:
                    pass
        logger.info("Both bots stopped (webhook)")

    @app.get("/health")
    async def health():
        return {"ok": True, "bots": ["monika", "sayori"]}

    async def _handle(request: Request, which: str):
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if which == "monika":
            if secret != SECRET_TOKEN_MONIKA:
                raise HTTPException(status_code=403, detail="Bad secret (monika)")
            bot_obj: Bot = holder["monika_bot"]  # type: ignore
            dp_obj: Dispatcher = holder["monika_dp"]  # type: ignore
        else:
            if secret != SECRET_TOKEN_SAYORI:
                raise HTTPException(status_code=403, detail="Bad secret (sayori)")
            bot_obj: Bot = holder["sayori_bot"]  # type: ignore
            dp_obj: Dispatcher = holder["sayori_dp"]  # type: ignore

        update = Update.model_validate(await request.json())
        await dp_obj.feed_update(bot_obj, update)
        return {"ok": True}

    @app.post(path_monika)
    async def monika_webhook(request: Request):
        return await _handle(request, "monika")

    @app.post(path_sayori)
    async def sayori_webhook(request: Request):
        return await _handle(request, "sayori")

    return app


# ================= MAIN =================
if __name__ == "__main__":
    mode = RUN_MODE.upper()
    logger.info(f"Starting multi-bot in {mode} mode")

    if mode in {"POLLING", "DEBUG"}:
        asyncio.run(run_polling_both())
    elif mode == "WEBHOOK":
        uvicorn.run("main:build_app", factory=True, host=HOST, port=int(PORT), reload=False)
    else:
        raise SystemExit(f"Unknown RUN_MODE: {RUN_MODE!r} (use POLLING / WEBHOOK / DEBUG)")

