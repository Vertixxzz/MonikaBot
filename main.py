from __future__ import annotations

import asyncio
import logging
import signal

from aiogram import Bot, Dispatcher, Router, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Update

from fastapi import FastAPI, Request, HTTPException
import uvicorn

from common.utils.links import register_bot
from common.db.core import connect_db, close_db
from common.db.pool import PoolMiddleware

# локалка
from cfg import (
    HOST,
    PORT,
    RUN_MODE,
    TARGET_CHAT_ID,
    BASE_URL,
    MONIKATOKEN,
    SAYORITOKEN,
    YURITOKEN,
    WEBHOOK_PATH_MONIKA,
    WEBHOOK_PATH_SAYORI,
    WEBHOOK_PATH_YURI,
    SECRET_TOKEN_MONIKA,
    SECRET_TOKEN_SAYORI,
    SECRET_TOKEN_YURI,
)

from monika.monika_register import (
    register_monika_handlers,
    register_monika_middlewares,
)
from sayori.sayori_register import (
    register_sayori_handlers,
    register_sayori_middlewares,
)
from yuri.yuri_register import register_yuri_handlers


# ================= LOGGING =================
DEBUG = RUN_MODE.upper() == "DEBUG"

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("multibot.main")


# ================= BUILD DISPATCHERS =================
async def build_dispatchers():
    monika_bot = Bot(token=MONIKATOKEN)
    sayori_bot = Bot(token=SAYORITOKEN)
    yuri_bot = Bot(token=YURITOKEN)

    monika_dp = Dispatcher(storage=MemoryStorage())
    sayori_dp = Dispatcher(storage=MemoryStorage())
    yuri_dp = Dispatcher(storage=MemoryStorage())

    if DEBUG:
        def add_debug_router(dp: Dispatcher):
            dbg = Router()

            @dbg.message()
            async def _dbg_log(m: types.Message):
                logger.debug(
                    "INCOMING: user=%s type=%s text=%r",
                    getattr(m.from_user, "id", None),
                    m.content_type,
                    getattr(m, "text", None),
                )

            dp.include_router(dbg)

        add_debug_router(monika_dp)
        add_debug_router(sayori_dp)
        add_debug_router(yuri_dp)

    pool = await connect_db()

    # --- Monika ---
    register_monika_middlewares(monika_dp, pool)
    monika_dp.update.outer_middleware(PoolMiddleware(pool))
    register_monika_handlers(monika_dp)

    # --- Sayori ---
    register_sayori_middlewares(sayori_dp)
    sayori_dp.update.outer_middleware(PoolMiddleware(pool))
    register_sayori_handlers(sayori_dp)

    # --- Yuri ---
    yuri_dp.update.outer_middleware(PoolMiddleware(pool))
    register_yuri_handlers(yuri_dp)

    register_bot("monika", monika_bot)
    register_bot("sayori", sayori_bot)
    register_bot("yuri", yuri_bot)

    logger.info("Dispatchers ready: Monika, Sayori, Yuri")

    return (
        monika_bot,
        monika_dp,
        sayori_bot,
        sayori_dp,
        yuri_bot,
        yuri_dp,
    )


# ================= POLLING =================
async def build_polling_side():
    (
        monika_bot,
        monika_dp,
        sayori_bot,
        sayori_dp,
        yuri_bot,
        yuri_dp,
    ) = await build_dispatchers()

    for bot, name in (
        (monika_bot, "monika"),
        (sayori_bot, "sayori"),
        (yuri_bot, "yuri"),
    ):
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted for %s (polling mode)", name)
        except Exception:
            logger.warning("Failed to delete webhook (%s)", name)

    return (
        monika_bot,
        monika_dp,
        sayori_bot,
        sayori_dp,
        yuri_bot,
        yuri_dp,
    )

async def run_polling_both():
    (
        monika_bot,
        monika_dp,
        sayori_bot,
        sayori_dp,
        yuri_bot,
        yuri_dp,
    ) = await build_polling_side()

    tasks = [
        asyncio.create_task(monika_dp.start_polling(monika_bot), name="monika_polling"),
        asyncio.create_task(sayori_dp.start_polling(sayori_bot), name="sayori_polling"),
        asyncio.create_task(yuri_dp.start_polling(yuri_bot), name="yuri_polling"),
        asyncio.create_task(_console(monika_bot, "Monika")),
        asyncio.create_task(_console(sayori_bot, "Sayori")),
        asyncio.create_task(_console(yuri_bot, "Yuri")),
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
        logger.info("Polling cancelled")
    finally:
        for bot, dp, name in (
            (monika_bot, monika_dp, "monika"),
            (sayori_bot, sayori_dp, "sayori"),
            (yuri_bot, yuri_dp, "yuri"),
        ):
            try:
                await bot.session.close()
            except Exception:
                logger.exception("Bot close failed (%s)", name)
            try:
                await dp.storage.close()
            except Exception:
                logger.exception("Storage close failed (%s)", name)

        logger.info("All bots stopped (polling)")


# ================= WEBHOOK =================
def build_app() -> FastAPI:
    app = FastAPI()
    holder: dict[str, object] = {}

    def norm(path: str) -> str:
        return path if path.startswith("/") else "/" + path

    path_monika = norm(WEBHOOK_PATH_MONIKA)
    path_sayori = norm(WEBHOOK_PATH_SAYORI)
    path_yuri = norm(WEBHOOK_PATH_YURI)

    @app.on_event("startup")
    async def on_startup():
        (
            monika_bot,
            monika_dp,
            sayori_bot,
            sayori_dp,
            yuri_bot,
            yuri_dp,
        ) = await build_dispatchers()

        holder.update(
            monika_bot=monika_bot,
            monika_dp=monika_dp,
            sayori_bot=sayori_bot,
            sayori_dp=sayori_dp,
            yuri_bot=yuri_bot,
            yuri_dp=yuri_dp,
        )

        for bot in (monika_bot, sayori_bot, yuri_bot):
            await bot.delete_webhook(drop_pending_updates=True)

        await monika_bot.set_webhook(
            f"{BASE_URL}{path_monika}",
            secret_token=SECRET_TOKEN_MONIKA,
        )
        await sayori_bot.set_webhook(
            f"{BASE_URL}{path_sayori}",
            secret_token=SECRET_TOKEN_SAYORI,
        )
        await yuri_bot.set_webhook(
            f"{BASE_URL}{path_yuri}",
            secret_token=SECRET_TOKEN_YURI,
        )

        logger.info("Webhooks set for all bots")

    @app.on_event("shutdown")
    async def on_shutdown():
        for key in ("monika_bot", "sayori_bot", "yuri_bot"):
            bot: Bot | None = holder.get(key)  # type: ignore
            if bot:
                try:
                    await bot.delete_webhook(drop_pending_updates=True)
                    await bot.session.close()
                except Exception:
                    pass

        for key in ("monika_dp", "sayori_dp", "yuri_dp"):
            dp: Dispatcher | None = holder.get(key)  # type: ignore
            if dp:
                try:
                    await dp.storage.close()
                except Exception:
                    pass

        await close_db()

        logger.info("All bots stopped (webhook)")

    async def _handle(request: Request, which: str):
        secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token")

        if which == "monika":
            if secret != SECRET_TOKEN_MONIKA:
                raise HTTPException(403)
            bot = holder["monika_bot"]
            dp = holder["monika_dp"]
        elif which == "sayori":
            if secret != SECRET_TOKEN_SAYORI:
                raise HTTPException(403)
            bot = holder["sayori_bot"]
            dp = holder["sayori_dp"]
        else:
            if secret != SECRET_TOKEN_YURI:
                raise HTTPException(403)
            bot = holder["yuri_bot"]
            dp = holder["yuri_dp"]

        update = Update.model_validate(await request.json())
        bg.add_task(dp.feed_update, bot, update)
        return {"ok": True}

    @app.post(path_monika)
    async def monika_webhook(request: Request):
        return await _handle(request, "monika")

    @app.post(path_sayori)
    async def sayori_webhook(request: Request):
        return await _handle(request, "sayori")

    @app.post(path_yuri)
    async def yuri_webhook(request: Request):
        return await _handle(request, "yuri")

    @app.get("/health")
    async def health():
        return {"ok": True, "bots": ["monika", "sayori", "yuri"]}

    return app


# ================= MAIN =================
if __name__ == "__main__":
    mode = RUN_MODE.upper()
    logger.info("Starting multi-bot in %s mode", mode)

    if mode in {"POLLING", "DEBUG"}:
        asyncio.run(run_polling_both())
    elif mode == "WEBHOOK":
        uvicorn.run(
            "main:build_app",
            factory=True,
            host=HOST,
            port=int(PORT),
            reload=False,
        )
    else:
        raise SystemExit(
            f"Unknown RUN_MODE: {RUN_MODE!r} (use POLLING / WEBHOOK / DEBUG)"
        )

