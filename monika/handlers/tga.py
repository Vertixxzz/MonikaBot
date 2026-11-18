"""Берлога Awards, этап 1: сбор номинантов в личке у Моники.

Команды (только в ЛС):
  моника опрос          — начать или продолжить опрос
  моника опрос заново   — стереть свои ответы и пройти заново
Во время опроса:
  пропустить            — оставить номинацию пустой
  стоп / отмена         — поставить на паузу (прогресс сохранён в БД)
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from common.db.tga import (
    QUESTIONS_COUNT,
    ensure_tga_table,
    tga_get,
    tga_reset,
    tga_save_reply,
    tga_start,
)
from .tga_questions import TGA_QUESTIONS

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.chat.type == "private")

MAX_REPLY_LEN = 300
SKIP_WORDS = {"пропустить", "пропуск", "скип", "-"}
STOP_WORDS = {"стоп", "отмена", "пауза"}

assert len(TGA_QUESTIONS) == QUESTIONS_COUNT, "Число вопросов не совпадает с колонками в БД"


class TgaPoll(StatesGroup):
    answering = State()


def _question_text(q_num: int) -> str:
    section, title, desc = TGA_QUESTIONS[q_num - 1]
    header = ""
    prev_section = TGA_QUESTIONS[q_num - 2][0] if q_num > 1 else None
    if section != prev_section:
        header = f"<b>{section}</b>\n\n"
    return (
        f"{header}<b>{q_num}/{QUESTIONS_COUNT}. {title}</b>\n"
        f"<i>{desc}</i>\n\n"
        f"Напиши своего номинанта (или «пропустить»)."
    )


async def _ask(message: Message, state: FSMContext, q_num: int) -> None:
    await state.set_state(TgaPoll.answering)
    await state.update_data(q_num=q_num)
    await message.answer(_question_text(q_num), parse_mode="HTML")


# ---------- старт / продолжение ----------

@router.message(F.text.lower().strip() == "моника опрос заново")
async def tga_restart(message: Message, state: FSMContext, pool):
    user = message.from_user
    await ensure_tga_table(pool)
    await tga_start(pool, user.id, user.username, user.full_name)
    await tga_reset(pool, user.id)
    await message.answer("Начинаем с чистого листа! 🌸")
    await _ask(message, state, 1)


@router.message(F.text.lower().strip() == "моника опрос")
async def tga_begin(message: Message, state: FSMContext, pool):
    user = message.from_user
    await ensure_tga_table(pool)

    existing = await tga_get(pool, user.id)
    if existing and existing["completed_at"] is not None:
        await state.clear()
        await message.answer(
            "Ты уже прошёл опрос, спасибо! 💚\n"
            "Если хочешь переголосовать — напиши «моника опрос заново»."
        )
        return

    q_num = await tga_start(pool, user.id, user.username, user.full_name)

    if q_num == 1:
        await message.answer(
            "Привет! Это первый этап <b>Берлога Awards</b> 🏆\n"
            f"Я задам {QUESTIONS_COUNT} вопросов — в каждой номинации напиши, кого ты предлагаешь.\n\n"
            "«пропустить» — пропустить номинацию\n"
            "«стоп» — пауза, потом продолжишь командой «моника опрос»",
            parse_mode="HTML",
        )
    else:
        await message.answer(f"Продолжаем с того места, где остановились ({q_num}/{QUESTIONS_COUNT})!")

    await _ask(message, state, q_num)


# ---------- ответы ----------

@router.message(StateFilter(TgaPoll.answering))
async def tga_answer(message: Message, state: FSMContext, pool):
    user = message.from_user
    data = await state.get_data()
    q_num: int = data.get("q_num", 1)

    text = (message.text or "").strip()
    if not text:
        await message.answer("Мне нужен текстовый ответ 🙂 Напиши номинанта или «пропустить».")
        return

    low = text.lower()
    if low in STOP_WORDS:
        await state.clear()
        await message.answer("Поставила на паузу. Продолжить — «моника опрос».")
        return

    if low in SKIP_WORDS:
        reply = None
    else:
        if len(text) > MAX_REPLY_LEN:
            await message.answer(f"Слишком длинно, уложись в {MAX_REPLY_LEN} символов.")
            return
        reply = text

    try:
        await tga_save_reply(pool, user.id, q_num, reply)
    except Exception:
        logger.exception("TGA: failed to save reply user=%s q=%s", user.id, q_num)
        await message.answer("Ой, не смогла сохранить ответ… попробуй ещё раз чуть позже.")
        return

    if q_num >= QUESTIONS_COUNT:
        await state.clear()
        await message.answer(
            "Готово! Все ответы записаны 💚\n"
            "Скоро будет второй этап — голосование за победителей."
        )
        return

    await _ask(message, state, q_num + 1)
