import logging
from aiogram import Router, types, F
from io import BytesIO
from PIL import Image
from aiogram.types import BufferedInputFile

from common.db.utilities import get_user_id_by_username

logger = logging.getLogger(__name__)
router = Router()


# ---------- utils ----------

async def get_user_avatar_file_id(bot, user_id: int) -> str | None:
    photos = await bot.get_user_profile_photos(user_id, limit=1)
    if photos.total_count == 0:
        return None
    return photos.photos[0][-1].file_id


async def get_legacy_avatar(bot, file_id: str) -> BufferedInputFile:
    file = await bot.get_file(file_id)

    buffer = BytesIO()
    await bot.download_file(file.file_path, buffer)
    buffer.seek(0)

    img = Image.open(buffer).convert("L")  # grayscale

    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)

    return BufferedInputFile(
        output.read(),
        filename="legacy.png"
    )



# ---------- handler ----------

@router.message(F.text.func(lambda t: t and t.lower().startswith("юри карточка")))
async def show_user_card(message: types.Message, pool):
    chat_id = message.chat.id
    author = message.from_user

    parts = message.text.strip().split(maxsplit=2)
    yours = False

    if len(parts) == 2:
        # юри карточка
        target_user_id = author.id
        target_name = author.full_name
        yours = True

    elif len(parts) == 3:
        # юри карточка <username>
        username = parts[2]

        target_user_id = await get_user_id_by_username(
            pool,
            username=username,
        )

        if not target_user_id:
            await message.answer(
                "Хм..\n"
                "Я не смогла найти этого человека в своих записях\n"
                "Возможно, он давно здесь не появлялся"
            )
            return

        target_name = username

    else:
        return


    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                rarity,
                percentile,
                messages_total,
                calculated_at,
                state
            FROM user_cards
            WHERE chat_id = $1
              AND user_id = $2
            """,
            chat_id,
            target_user_id,
        )

    if not row:
        await message.answer(
            "Хм..\n"
            "Я пока ещё не успела собрать достаточно данных\n"
            "Попробуй заглянуть позже"
        )
        return


    rarity = row["rarity"]
    state = row["state"]
    percentile = row["percentile"] * 100
    messages = row["messages_total"]
    calculated_at = row["calculated_at"]


    if state == "LEGACY":
        rarity_text = f"{rarity}, LEGACY ️"
        footer = (
            "\n\n_Эта карточка больше не создаётся._\n"
            "_Но я всё ещё её помню._"
        )
    else:
        rarity_text = rarity
        footer = ""

    header = "Твоя карточка" if yours else f"Карточка {target_name}"

    caption = (
        f"*{header}*\n\n"
        f"Редкость: *{rarity_text}*\n"
        f"Сообщений учтено: `{messages}`\n"
        f"Активнее, чем ~`{percentile:.1f}%` участников этого чата\n\n"
        f"_Последнее обновление: {calculated_at:%d.%m.%Y}_"
        f"{footer}"
    )


    avatar_file_id = await get_user_avatar_file_id(message.bot, target_user_id)

    try:
        if avatar_file_id and state == "LEGACY":
            photo = await get_legacy_avatar(message.bot, avatar_file_id)
            await message.answer_photo(
                photo=photo,
                caption=caption,
                parse_mode="Markdown",
            )

        elif avatar_file_id:
            await message.answer_photo(
                photo=avatar_file_id,
                caption=caption,
                parse_mode="Markdown",
            )

        else:
            await message.answer(
                caption,
                parse_mode="Markdown",
            )

    except Exception:
        logger.exception("Failed to send Yuri card")
        await message.answer(
            caption,
            parse_mode="Markdown",
        )


