from __future__ import annotations
import logging
from aiogram import Dispatcher, Router

from .middlewares.messagestats import MessageStatsMiddleware
from .handlers.greetings import register_greetings

from .handlers.stats import router as stats_router
from .handlers.help import router as help_router
from .handlers.garem import router as garem_router
from .handlers.day import router as day_router
from .handlers.beer import router as beer_router
from .handlers.dinki import router as dinki_router
from .handlers.speech_rec import router as sr_router
from .handlers.translate import router as translate_router
from .handlers.alive import router as alive_router
from .handlers.ecomoniks import router as ec_router
from .handlers.warn import router as warn_router
from .handlers.remember import router as remember_router
from .handlers.antiiris import router as antiiris_router
from .handlers.silence import router as silence_router
from .handlers.weather import router as weather_router
from .handlers.spam import router as spam_router
from .handlers.brutemute import router as anton_router
from .handlers.openai import router as openai_router
from .handlers.promo import router as promo_router

logger = logging.getLogger(__name__)


def register_monika_middlewares(dp: Dispatcher, pool) -> None:
    dp.message.middleware(MessageStatsMiddleware(pool))
    logger.info("Middlewares registered (message_stats)")


def register_monika_handlers(dp: Dispatcher) -> None:
    register_greetings(dp)

    routers: tuple[Router, ...] = (
        promo_router,
        openai_router,
        weather_router,
        stats_router,
        help_router,
        garem_router,
        day_router,
        beer_router,
        dinki_router,
        sr_router,
        translate_router,
        alive_router,
        ec_router,
        warn_router,
        remember_router,
        antiiris_router,
        spam_router,
        anton_router,
    )

    for r in routers:
        dp.include_router(r)

    logger.info("Handlers registered (functions: 1, routers: %d)", len(routers))



