"""Берлога Awards: просмотр ответов для организаторов (только ЛС, только TGA_ADMINS).

  тга помощь              — список команд
  тга стата               — сколько человек начали/закончили, заполненность номинаций
  тга номинации           — список номинаций с номерами
  тга номинация <N>       — топ номинантов и кто что ответил в номинации N
  тга анкета <@ник|id>    — все ответы одного человека
  тга выгрузка            — CSV-файл со всеми ответами
"""
from __future__ import annotations

import csv
import io
import os
import re
from collections import Counter
from datetime import datetime
from html import escape

from aiogram import F, Router
from aiogram.types import BufferedInputFile, Message

from common.db.tga import QUESTIONS_COUNT, REPLY_COLUMNS, ensure_tga_table, tga_all, tga_find
from .tga_questions import TGA_QUESTIONS

try:
    from cfg import TGA_ADMINS
except ImportError:  # cfg.py на сервере не обновлён — читаем прямо из .env
    TGA_ADMINS = [
        int(x) for x in os.getenv("TGA_ADMINS", "").replace(" ", "").split(",")
        if x.lstrip("-").isdigit()
    ]

router = Router()
# Не-админы и не-ЛС проваливаются дальше (например, в сам опрос), а не получают отказ
router.message.filter(F.chat.type == "private", F.from_user.id.in_(set(TGA_ADMINS)))

MSG_LIMIT = 3800


# ---------- хелперы ----------

def _who(row) -> str:
    if row["username"]:
        return f"@{escape(row['username'])}"
    name = escape(row["full_name"] or "без имени")
    return f'<a href="tg://user?id={row["user_id"]}">{name}</a>'


def _norm(answer: str) -> str:
    """Ключ для подсчёта: «@Vasya», «vasya » и «VASYA» считаются одним номинантом."""
    return re.sub(r"\s+", " ", answer.strip().lstrip("@").lower())


async def _send_long(message: Message, lines: list[str]) -> None:
    """Режет длинный текст на сообщения по строкам, чтобы не упереться в лимит Telegram."""
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > MSG_LIMIT and chunk:
            await message.answer(chunk, parse_mode="HTML", disable_web_page_preview=True)
            chunk = ""
        chunk += line + "\n"
    if chunk.strip():
        await message.answer(chunk, parse_mode="HTML", disable_web_page_preview=True)


def _cmd(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


# ---------- команды ----------

@router.message(F.text.func(lambda t: _cmd(t) in {"тга", "тга помощь"}))
async def tga_help(message: Message):
    await message.answer(
        "<b>Берлога Awards — админка</b>\n\n"
        "тга стата — сколько человек прошли опрос\n"
        "тга номинации — список номинаций с номерами\n"
        "тга номинация &lt;N&gt; — топ номинантов и кто что ответил\n"
        "тга анкета &lt;@ник|id&gt; — все ответы одного человека\n"
        "тга выгрузка — CSV со всеми ответами",
        parse_mode="HTML",
    )


@router.message(F.text.func(lambda t: _cmd(t) == "тга стата"))
async def tga_stats(message: Message, pool):
    await ensure_tga_table(pool)
    rows = await tga_all(pool)
    done = sum(1 for r in rows if r["completed_at"] is not None)

    lines = [
        "<b>Берлога Awards — статистика</b>",
        f"Начали опрос: {len(rows)}",
        f"Завершили: {done}",
        f"В процессе: {len(rows) - done}",
        "",
        "<b>Ответов по номинациям:</b>",
    ]
    for i, (_, title, _) in enumerate(TGA_QUESTIONS, start=1):
        col = REPLY_COLUMNS[i - 1]
        filled = sum(1 for r in rows if r[col])
        lines.append(f"{i}. {escape(title)} — {filled}")

    await _send_long(message, lines)


@router.message(F.text.func(lambda t: _cmd(t) == "тга номинации"))
async def tga_list(message: Message):
    lines = ["<b>Номинации:</b>"]
    section = None
    for i, (sec, title, _) in enumerate(TGA_QUESTIONS, start=1):
        if sec != section:
            section = sec
            lines.append(f"\n<b>{escape(sec)}</b>")
        lines.append(f"{i}. {escape(title)}")
    await _send_long(message, lines)


@router.message(F.text.func(lambda t: _cmd(t).startswith("тга номинация")))
async def tga_nomination(message: Message, pool):
    arg = _cmd(message.text).removeprefix("тга номинация").strip()
    if not arg.isdigit() or not 1 <= int(arg) <= QUESTIONS_COUNT:
        await message.answer(f"Формат: тга номинация &lt;1–{QUESTIONS_COUNT}&gt;", parse_mode="HTML")
        return

    n = int(arg)
    col = REPLY_COLUMNS[n - 1]
    _, title, _ = TGA_QUESTIONS[n - 1]

    await ensure_tga_table(pool)
    rows = [r for r in await tga_all(pool) if r[col]]

    if not rows:
        await message.answer(f"В номинации «{escape(title)}» пока нет ответов.", parse_mode="HTML")
        return

    counts: Counter[str] = Counter()
    display: dict[str, str] = {}  # нормализованный ключ -> как написал первый ответивший
    for r in rows:
        key = _norm(r[col])
        counts[key] += 1
        display.setdefault(key, r[col].strip())

    lines = [f"<b>{n}. {escape(title)}</b> — ответов: {len(rows)}", "", "<b>Топ номинантов:</b>"]
    for key, cnt in counts.most_common():
        lines.append(f"{cnt} — {escape(display[key])}")

    lines += ["", "<b>Кто что ответил:</b>"]
    for r in rows:
        lines.append(f"{_who(r)}: {escape(r[col])}")

    await _send_long(message, lines)


@router.message(F.text.func(lambda t: _cmd(t).startswith("тга анкета")))
async def tga_profile(message: Message, pool):
    m = re.match(r"(?is)^\s*тга\s+анкета\s*(.*)$", message.text or "")
    arg = m.group(1).strip() if m else ""
    if not arg:
        await message.answer("Формат: тга анкета &lt;@ник или id&gt;", parse_mode="HTML")
        return

    await ensure_tga_table(pool)
    row = await tga_find(pool, arg)
    if not row:
        await message.answer("Не нашла анкету этого человека.")
        return

    status = (
        f"завершена {row['completed_at']:%d.%m %H:%M}"
        if row["completed_at"]
        else f"в процессе (вопрос {row['current_q']}/{QUESTIONS_COUNT})"
    )
    lines = [f"<b>Анкета</b> {_who(row)} (id {row['user_id']})", f"Статус: {status}", ""]
    for i, (_, title, _) in enumerate(TGA_QUESTIONS, start=1):
        val = row[REPLY_COLUMNS[i - 1]]
        lines.append(f"{i}. <b>{escape(title)}</b>: {escape(val) if val else '—'}")

    await _send_long(message, lines)


@router.message(F.text.func(lambda t: _cmd(t) == "тга выгрузка"))
async def tga_export(message: Message, pool):
    await ensure_tga_table(pool)
    rows = await tga_all(pool)
    if not rows:
        await message.answer("Пока никто не отвечал.")
        return

    buf = io.StringIO()
    # «;» + BOM — чтобы русский Excel открыл файл без танцев с кодировкой
    w = csv.writer(buf, delimiter=";")
    w.writerow(
        ["user_id", "username", "full_name", "завершено"]
        + [f"{i}. {t}" for i, (_, t, _) in enumerate(TGA_QUESTIONS, start=1)]
    )
    for r in rows:
        w.writerow(
            [
                r["user_id"],
                r["username"] or "",
                r["full_name"] or "",
                f"{r['completed_at']:%Y-%m-%d %H:%M}" if r["completed_at"] else "",
            ]
            + [r[col] or "" for col in REPLY_COLUMNS]
        )

    data = buf.getvalue().encode("utf-8-sig")
    filename = f"berloga_awards_{datetime.now():%Y%m%d_%H%M}.csv"
    await message.answer_document(
        BufferedInputFile(data, filename=filename),
        caption=f"Анкет: {len(rows)}",
    )
