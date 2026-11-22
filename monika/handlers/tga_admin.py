"""Берлога Awards: просмотр ответов для организаторов (только ЛС, только TGA_ADMINS).

  тга помощь              — список команд
  тга стата               — сколько человек начали/закончили, заполненность номинаций
  тга номинации           — список номинаций с номерами
  тга номинация <N>       — топ номинантов и кто что ответил в номинации N
  тга анкета <@ник|id>    — все ответы одного человека
  тга выгрузка            — CSV-файл со всеми ответами

Этап 2 (голосование по шорт-листу):
  тга сбор открыть|закрыть         — сбор номинантов (этап 1) вкл/выкл
  тга голосование открыть|закрыть  — голосование (этап 2) вкл/выкл
  тга ссылка                       — ссылка «в одно нажатие» для анонса
  тга голосовавшие                 — кто проголосовал, кто ещё в процессе
  тга итоги                        — голоса по всем номинациям
  тга итоги <N>                    — номинация N: кто за кого голосовал
  тга бюллетень <@ник|id>          — все голоса одного человека
  тга голоса выгрузка              — два CSV: голоса каждого и итоги
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

from common.db.tga import (
    QUESTIONS_COUNT,
    REPLY_COLUMNS,
    STAGE1_OPEN,
    VOTE_OPEN,
    ensure_tga_table,
    tga_all,
    tga_find,
    tga_setting_get,
    tga_setting_set,
    vote_all_voters,
    vote_all_votes,
    vote_find_voter,
    vote_get_choices,
)
from .tga_finalists import FINAL_COUNT, TGA_FINAL
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
        "тга выгрузка — CSV со всеми ответами\n\n"
        "<b>Этап 2 — голосование</b>\n"
        "тга сбор открыть|закрыть — сбор номинантов\n"
        "тга голосование открыть|закрыть — голосование\n"
        "тга ссылка — ссылка на голосование для анонса\n"
        "тга голосовавшие — кто голосовал\n"
        "тга итоги — голоса по всем номинациям\n"
        "тга итоги &lt;N&gt; — кто за кого в номинации N\n"
        "тга бюллетень &lt;@ник|id&gt; — голоса одного человека\n"
        "тга голоса выгрузка — CSV голосов и итогов",
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


# =====================================================================
#  Этап 2: голосование по шорт-листу
# =====================================================================

_SWITCHES = {"сбор": (STAGE1_OPEN, "Сбор номинантов"), "голосование": (VOTE_OPEN, "Голосование")}
_STATES = {"открыть": True, "закрыть": False}


def _pick(n: int, choice: int | None) -> str:
    """Текст ответа в номинации n: «имя - @ник», «(пропуск)» или «?» для битого номера."""
    if choice is None:
        return "(пропуск)"
    finalists = TGA_FINAL[n - 1].finalists
    return finalists[choice].label if 0 <= choice < len(finalists) else "?"


async def _tally(pool):
    """Считает голоса: (голосующие по id, picks[user][n], counts[n][choice], пропуски[n])."""
    voters = {int(v["user_id"]): v for v in await vote_all_voters(pool)}
    picks: dict[int, dict[int, int | None]] = {}
    counts: dict[int, Counter[int]] = {n: Counter() for n in range(1, FINAL_COUNT + 1)}
    skips: dict[int, int] = {n: 0 for n in range(1, FINAL_COUNT + 1)}
    for v in await vote_all_votes(pool):
        uid, n, choice = int(v["user_id"]), int(v["nomination"]), v["choice"]
        if n not in counts:
            continue
        picks.setdefault(uid, {})[n] = choice
        if choice is None:
            skips[n] += 1
        elif 0 <= choice < len(TGA_FINAL[n - 1].finalists):
            counts[n][int(choice)] += 1
    return voters, picks, counts, skips


def _ranked(n: int, c: Counter[int]) -> tuple[list[int], set[int]]:
    """Финалисты по убыванию голосов и множество лидеров (несколько — ничья)."""
    ranked = sorted(range(len(TGA_FINAL[n - 1].finalists)), key=lambda i: (-c[i], i))
    top = c[ranked[0]] if ranked else 0
    return ranked, {i for i in ranked if top > 0 and c[i] == top}


@router.message(F.text.func(lambda t: bool(re.fullmatch(r"тга (сбор|голосование) (открыть|закрыть)", _cmd(t)))))
async def tga_switch(message: Message, pool):
    _, what, how = _cmd(message.text).split(" ")
    key, title = _SWITCHES[what]
    await tga_setting_set(pool, key, _STATES[how])
    stage1 = await tga_setting_get(pool, STAGE1_OPEN)
    vote = await tga_setting_get(pool, VOTE_OPEN)
    await message.answer(
        f"{title}: {'открыто ✅' if _STATES[how] else 'закрыто ⛔'}\n\n"
        f"Сейчас — сбор номинантов: {'открыт' if stage1 else 'закрыт'}, "
        f"голосование: {'открыто' if vote else 'закрыто'}"
    )


@router.message(F.text.func(lambda t: _cmd(t) == "тга ссылка"))
async def tga_link(message: Message):
    me = await message.bot.me()
    await message.answer(
        "Ссылка на голосование — открывает личку Моники и сразу запускает его:\n"
        f"https://t.me/{me.username}?start=vote"
    )


@router.message(F.text.func(lambda t: _cmd(t) == "тга голосовавшие"))
async def tga_voters_list(message: Message, pool):
    voters, picks, _, _ = await _tally(pool)
    if not voters:
        await message.answer("Пока никто не голосовал.")
        return

    vote_open = await tga_setting_get(pool, VOTE_OPEN)
    done = [v for v in voters.values() if v["completed_at"] is not None]
    pending = [v for v in voters.values() if v["completed_at"] is None]

    lines = [
        f"<b>Голосование {'открыто ✅' if vote_open else 'закрыто ⛔'}</b>",
        "",
        f"<b>Проголосовали во всех номинациях ({len(done)}):</b>",
    ]
    lines += [
        f"{_who(v)} — {v['completed_at']:%d.%m %H:%M}" for v in done
    ] or ["—"]
    lines += ["", f"<b>В процессе ({len(pending)}):</b>"]
    lines += [
        f"{_who(v)} — {len(picks.get(int(v['user_id']), {}))}/{FINAL_COUNT}" for v in pending
    ] or ["—"]
    await _send_long(message, lines)


@router.message(F.text.func(lambda t: bool(re.fullmatch(r"тга итоги( \d+)?", _cmd(t)))))
async def tga_results(message: Message, pool):
    arg = _cmd(message.text).removeprefix("тга итоги").strip()
    voters, picks, counts, skips = await _tally(pool)

    # ---- одна номинация: кто за кого ----
    if arg:
        n = int(arg)
        if not 1 <= n <= FINAL_COUNT:
            await message.answer(f"Формат: тга итоги &lt;1–{FINAL_COUNT}&gt;", parse_mode="HTML")
            return
        nom = TGA_FINAL[n - 1]
        c = counts[n]
        ranked, leaders = _ranked(n, c)

        lines = [f"<b>{n}. {escape(nom.title)}</b> — голосов: {sum(c.values())}, пропусков: {skips[n]}"]
        for i in ranked:
            who = [voters[uid] for uid, p in picks.items() if p.get(n) == i and uid in voters]
            lines += [
                "",
                f"{'🥇 ' if i in leaders else ''}<b>{c[i]}</b> — {escape(nom.finalists[i].label)}",
                ", ".join(_who(v) for v in who) if who else "<i>никто</i>",
            ]
        skipped = [voters[uid] for uid, p in picks.items() if n in p and p[n] is None and uid in voters]
        if skipped:
            lines += ["", "<b>Пропустили:</b> " + ", ".join(_who(v) for v in skipped)]
        if len(leaders) > 1:
            lines += ["", "⚠️ Ничья"]
        await _send_long(message, lines)
        return

    # ---- все номинации ----
    vote_open = await tga_setting_get(pool, VOTE_OPEN)
    done = sum(1 for v in voters.values() if v["completed_at"] is not None)
    lines = [
        "<b>Берлога Awards — итоги голосования</b>",
        f"Голосование: {'открыто' if vote_open else 'закрыто'}",
        f"Голосуют: {len(voters)}, ответили во всех номинациях: {done}",
        "<i>Считаются все поданные голоса, в том числе у тех, кто не дошёл до конца. "
        "Кто за кого — «тга итоги N».</i>",
    ]
    for n, nom in enumerate(TGA_FINAL, start=1):
        c = counts[n]
        ranked, leaders = _ranked(n, c)
        lines += ["", f"<b>{n}. {escape(nom.title)}</b> — голосов: {sum(c.values())}"]
        for i in ranked:
            lines.append(f"{'🥇 ' if i in leaders else ''}{c[i]} — {escape(nom.finalists[i].label)}")
        if len(leaders) > 1:
            lines.append("⚠️ ничья")
    await _send_long(message, lines)


@router.message(F.text.func(lambda t: _cmd(t).startswith("тга бюллетень")))
async def tga_ballot(message: Message, pool):
    m = re.match(r"(?is)^\s*тга\s+бюллетень\s*(.*)$", message.text or "")
    arg = m.group(1).strip() if m else ""
    if not arg:
        await message.answer("Формат: тга бюллетень &lt;@ник или id&gt;", parse_mode="HTML")
        return

    voter = await vote_find_voter(pool, arg)
    if not voter:
        await message.answer("Этот человек ещё не голосовал (или ник другой — попробуй по id).")
        return

    choices = await vote_get_choices(pool, int(voter["user_id"]))
    status = (
        f"во всех номинациях с {voter['completed_at']:%d.%m %H:%M}"
        if voter["completed_at"]
        else f"в процессе ({len(choices)}/{FINAL_COUNT})"
    )
    lines = [f"<b>Бюллетень</b> {_who(voter)} (id {voter['user_id']})", f"Статус: {status}", ""]
    for n, nom in enumerate(TGA_FINAL, start=1):
        value = escape(_pick(n, choices[n])) if n in choices else "—"
        lines.append(f"{n}. <b>{escape(nom.title)}</b>: {value}")
    await _send_long(message, lines)


@router.message(F.text.func(lambda t: _cmd(t) == "тга голоса выгрузка"))
async def tga_votes_export(message: Message, pool):
    voters, picks, counts, skips = await _tally(pool)
    if not voters:
        await message.answer("Пока никто не голосовал.")
        return

    stamp = f"{datetime.now():%Y%m%d_%H%M}"

    # 1) голоса каждого: строка = человек, колонка = номинация
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(
        ["user_id", "username", "full_name", f"ответов из {FINAL_COUNT}", "все номинации"]
        + [f"{n}. {nom.title}" for n, nom in enumerate(TGA_FINAL, start=1)]
    )
    for uid, v in voters.items():
        p = picks.get(uid, {})
        w.writerow(
            [
                uid,
                v["username"] or "",
                v["full_name"] or "",
                len(p),  # число, а не «7/20»: Excel превратил бы «1/20» в дату
                f"{v['completed_at']:%Y-%m-%d %H:%M}" if v["completed_at"] else "",
            ]
            + [_pick(n, p[n]) if n in p else "" for n in range(1, FINAL_COUNT + 1)]
        )
    await message.answer_document(
        BufferedInputFile(buf.getvalue().encode("utf-8-sig"), filename=f"berloga_votes_{stamp}.csv"),
        caption=f"Голоса каждого. Голосующих: {len(voters)}",
    )

    # 2) итоги: строка = финалист
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["№", "номинация", "финалист", "голосов", "лидер"])
    for n, nom in enumerate(TGA_FINAL, start=1):
        c = counts[n]
        ranked, leaders = _ranked(n, c)
        for i in ranked:
            lead = ("ничья" if len(leaders) > 1 else "да") if i in leaders else ""
            w.writerow([n, nom.title, nom.finalists[i].label, c[i], lead])
        w.writerow([n, nom.title, "(пропуск)", skips[n], ""])
    await message.answer_document(
        BufferedInputFile(buf.getvalue().encode("utf-8-sig"), filename=f"berloga_results_{stamp}.csv"),
        caption="Итоги по номинациям",
  )
