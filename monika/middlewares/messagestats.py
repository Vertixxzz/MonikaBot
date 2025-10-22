from aiogram import BaseMiddleware
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import Message
from datetime import datetime

class MessageStatsMiddleware(BaseMiddleware):
    def __init__(self, pool):
        self.pool = pool

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        pool = self.pool
        user = event.from_user
        chat_id = event.chat.id
        
        if not user or user.is_bot or not event.text:
            return await handler(event, data)

        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_stats (user_id, chat_id, username, messages_today, messages_total, last_message_date)
                VALUES ($1, $2, $3, 1, 1, CURRENT_DATE)
                ON CONFLICT (user_id, chat_id)
                DO UPDATE SET
                    messages_total = user_stats.messages_total + 1,
                    messages_today = CASE 
                        WHEN user_stats.last_message_date = CURRENT_DATE 
                            THEN user_stats.messages_today + 1
                        ELSE 1
                    END,
                    last_message_date = CURRENT_DATE,
                    username = EXCLUDED.username
            """, user.id, chat_id, user.username or user.full_name)

        return await handler(event, data)
