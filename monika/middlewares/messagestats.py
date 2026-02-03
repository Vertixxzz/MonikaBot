from aiogram import BaseMiddleware
from typing import Callable, Awaitable, Dict, Any
from aiogram.types import Message


class MessageStatsMiddleware(BaseMiddleware):
    def __init__(self, pool):
        self.pool = pool

    async def __call__(
        self,
        handler: Callable[[Message, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        user = event.from_user

        if not user or user.is_bot or not event.text:
            return await handler(event, data)

        chat_id = event.chat.id
        pool = self.pool

        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_stats (
                    user_id,
                    chat_id,
                    username,
                    messages_today,
                    messages_total,
                    last_message_date,
                    ispresent,
                    messagefromcontest
                )
                VALUES ($1, $2, $3, 1, 1, CURRENT_DATE, TRUE, 1)
                ON CONFLICT (user_id, chat_id)
                DO UPDATE SET
                    messages_total = user_stats.messages_total + 1,
                    messages_today = CASE 
                        WHEN user_stats.last_message_date = CURRENT_DATE 
                            THEN user_stats.messages_today + 1
                        ELSE 1
                    END,
                    messagefromcontest = user_stats.messagefromcontest + 1,
                    last_message_date = CURRENT_DATE,
                    username = EXCLUDED.username,
                    ispresent = TRUE
                """,
                user.id,
                chat_id,
                user.username or user.full_name,
            )

        return await handler(event, data)
