from __future__ import annotations
import logging
from aiogram import Dispatcher, Router

from .handlers.greetings import register_greetings
from .handlers.roleplay import router as roleplay_router
from .handlers.hangman import router as hangman_router
from .handlers.duels import router as duels_router
from .handlers.help import router as help_router
from aiogram import Dispatcher

logger = logging.getLogger(__name__)

def register_sayori_middlewares(dp: Dispatcher):
    pass

def register_sayori_handlers(dp: Dispatcher) -> None:
    register_greetings(dp)

    routers: tuple[Router, ...] = (
        help_router,
        hangman_router,
        roleplay_router,
    )

    for r in routers:
        dp.include_router(r)

    logger.info("Handlers registered (functions: 1, routers: %d)", len(routers))

