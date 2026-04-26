from aiogram import Router, F
from aiogram.exceptions import TelegramBadRequest

from common.db.warnings import (
    add_warning,
    get_warnings,
    clear_warnings,
    remove_one_warning,
    get_warning_events,
)

from common.utils.manage import (
    MSK,
    require_bot_admin,
    who_label,
    tg_human_error,
    deny_if_self,
    extract_reason_from_second_line,
    resolve_target_user,
)

router = Router()


@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "варн")
async def warn_user_handler(message, pool):
    if not await require_bot_admin(pool, message.chat.id, message.from_user.id):
        message.reply("Ты не админ этого чата!")
        return

    chat_id = message.chat.id
    lines = (message.text or "").splitlines()

    if message.reply_to_message:
        u = message.reply_to_message.from_user
        target_id = u.id
        username = u.username or u.full_name
    else:
        parts = lines[0].split()
        if len(parts) < 2:
            await message.answer(
                "Укажи пользователя реплаем или так: `варн @username`.\n"
                "Причину можно второй строкой."
            )
            return

        username = parts[1].lstrip("@")
        user_id, _ = await resolve_target_user(message, pool, username_pos=1)
        target_id = user_id

        if not target_id:
            await message.answer("Не удалось найти пользователя.")
            return

    reason = extract_reason_from_second_line(message) or "нарушение правил"

    await add_warning(pool, target_id, username, chat_id, reason)
    data = await get_warnings(pool, target_id, chat_id)
    count = data["count"]

    if count >= 3:
        try:
            if await deny_if_self(message, target_id, "забанить"):
                return
            await message.bot.ban_chat_member(chat_id=chat_id, user_id=target_id)
            await clear_warnings(pool, target_id, chat_id)
            await message.answer(
                f"{who_label(username)} получил 3 предупреждения и был забанен.\n"
                f"Причина последнего нарушения: {reason}"
            )
        except TelegramBadRequest as e:
            await message.answer(tg_human_error(e))
            await clear_warnings(pool, target_id, chat_id)
    else:
        await message.answer(
            f"{who_label(username)} получил предупреждение.\n"
            f"Причина: {reason}\n"
            f"Всего предупреждений: {count}/3"
        )


@router.message(F.text.lower().startswith("снять варн"))
async def warn_user_snyat(message, pool):
    if not await require_bot_admin(pool, message.chat.id, message.from_user.id):
        message.reply("Ты не админ этого чата!")
        return

    chat_id = message.chat.id

    if message.reply_to_message:
        u = message.reply_to_message.from_user
        user_id = u.id
        username = u.username or u.full_name
    else:
        parts = (message.text or "").split()
        if len(parts) < 3:
            await message.answer("Укажи пользователя: `снять варн @username` (или реплаем).")
            return

        username = parts[2].lstrip("@")
        user_id, _ = await resolve_target_user(message, pool, username_pos=2)
        if not user_id:
            await message.answer("Не удалось найти пользователя.")
            return

    data = await get_warnings(pool, user_id, chat_id)
    if not data or data["count"] == 0:
        await message.answer("У данного пользователя нет варнов.")
        return

    await remove_one_warning(pool, user_id, username, chat_id)
    await message.answer(f"С пользователя {who_label(username)} был снят 1 варн.")


@router.message(lambda msg: msg.text and msg.text.lower().split()[0] == "варны")
async def showwarn_handler(message, pool):
    chat_id = message.chat.id

    if message.reply_to_message:
        u = message.reply_to_message.from_user
        user_id = u.id
        username = u.username or u.full_name
    else:
        parts = (message.text or "").split()
        if len(parts) < 2:
            await message.answer("Укажи пользователя: `варны @username` (или реплаем).")
            return

        username = parts[1].lstrip("@")
        user_id, _ = await resolve_target_user(message, pool, username_pos=1)
        if not user_id:
            await message.answer("Не удалось найти пользователя.")
            return

    data = await get_warnings(pool, user_id, chat_id)
    if not data or data["count"] == 0:
        await message.answer("У данного пользователя нет варнов.")
        return

    events = await get_warning_events(pool, user_id, chat_id, limit=10)

    lines = []
    for i, e in enumerate(events, start=1):
        reason = (e["reason"] or "Нарушение правил").strip()
        dt = e["warned_at"].astimezone(MSK)
        dt_str = dt.strftime("%d.%m.%Y %H:%M")
        lines.append(f"{i}) `{dt_str} МСК` - {reason}")

    await message.answer(
        f"У пользователя {who_label(username)} {data['count']} варнов.\n"
        f"Последние {len(lines)}:\n" + "\n".join(lines)
    )