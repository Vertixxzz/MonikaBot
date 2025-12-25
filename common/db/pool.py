from aiogram import BaseMiddleware
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import TelegramObject
import asyncpg

class PoolMiddleware(BaseMiddleware):
    def __init__(self, pool: asyncpg.Pool):
        super().__init__()
        self.pool = pool

    async def __call__(self, handler, event: TelegramObject, data: Dict[str, Any]) -> Any:
        data["pool"] = self.pool
        return await handler(event, data)
