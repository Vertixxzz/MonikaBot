from __future__ import annotations
import logging
from aiogram import Dispatcher, Router

from .handlers.help import router as help_router
from .handlers.card import router as card_router
from .handlers.recalculate import router as recalculate_router
from .handlers.gacha import router as gacha_router

logger = logging.getLogger(__name__)

def register_yuri_middlewares(dp: Dispatcher):
    pass

def register_yuri_handlers(dp: Dispatcher) -> None:

    routers: tuple[Router, ...] = (
        gacha_router,
        help_router,
        card_router,
        recalculate_router,
    )

    for r in routers:
        dp.include_router(r)

    logger.info("Handlers registered (functions: 1, routers: %d)", len(routers))
