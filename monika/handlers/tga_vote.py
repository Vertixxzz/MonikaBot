"""Берлога Awards, этап 2: голосование за финалистов в личке у Моники.

Команды (в ЛС):
  моника голосование          — начать или продолжить с первой номинации без ответа
  моника голосование заново   — пройти все номинации с начала: прошлые голоса отмечены ✅,
                                их можно оставить или поменять (ничего не стирается)
  моника мои голоса           — сводка своих голосов
  t.me/<бот>?start=vote       — то же, что «моника голосование», в одно нажатие
                                (кнопку с этой ссылкой Моника даёт в чате, ссылка: «тга ссылка»)

Дальше всё на инлайн-кнопках. FSM не используется: прогресс считается по БД,
поэтому перезапуск контейнера посреди голосования ничего не ломает.

callback_data (лимит Telegram — 64 байта, у нас максимум ~12):
  tv:v:<n>:<i>:<mode>  голос в номинации n за финалиста i (номер в tga_finalists, с 0)
  tv:s:<n>:<mode>      пропустить номинацию n (choice = NULL)
  tv:g:<n>:<mode>      просто открыть номинацию n (листание, без записи)
  tv:sum               сводка «мои голоса»
  tv:done              закрыть сводку (убрать кнопки)

mode — куда идти после голоса:
  f  обычный проход: к следующей номинации без ответа; если таких нет — к сводке
  r  «заново»: строго к следующей по номеру; после последней — к сводке
  e  правка из сводки: сразу обратно к сводке
"""
from __future__ import annotations

import logging
import os
import random
import re
from html import escape

from aiogram import Bot, Dispatcher, F, Router
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNotFound,
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from common.db.tga import (
    VOTE_OPEN,
    tga_setting_get,
    vote_get_choices,
    vote_get_voter,
    vote_save,
    vote_start,
)
from .tga_admin import TGA_ADMINS
from .tga_finalists import FINAL_COUNT, TGA_FINAL, Nomination

try:
    from cfg import TARGET_CHAT_ID
except ImportError:  # как в tga_admin: если cfg.py на сервере старый — берём из .env
    TARGET_CHAT_ID = int(os.getenv("TARGET_CHAT_ID", "0") or 0)

logger = logging.getLogger(__name__)

router = Router()

PRIVATE = F.chat.type == "private"
DEEP_LINK_ARG = "vote"

START_COMMANDS = {"моника голосование", "моника голосовать"}
AGAIN_COMMANDS = {"моника голосование заново", "моника голосовать заново"}
MINE_COMMANDS = {"моника мои голоса"}
ALL_COMMANDS = START_COMMANDS | AGAIN_COMMANDS | MINE_COMMANDS

MODES = {"f", "r", "e"}
BUTTON_MAX = 48      # длиннее — обрезаем с «…»
LIST_IF_LONGER = 30  # если хоть одна кнопка длиннее — дублируем варианты текстом над кнопками

INTRO_TEXT = (
    "🏆 <b>Финал Берлога Awards</b>\n\n"
    f"{FINAL_COUNT} номинаций, в каждой выбери победителя кнопкой.\n"
    "• голос сохраняется сразу, поменять его можно до конца голосования;\n"
    "• «Пропустить» — если не хочешь голосовать в номинации;\n"
    "• ⬅️ ➡️ листают номинации, 📋 показывает все твои голоса;\n"
    "• голосовать можно и за себя;\n"
    "• кто за кого голосовал, видят только организаторы, публично будут только итоги."
)
CLOSED_TEXT = "Голосование сейчас закрыто 🔒 Следи за анонсами в чате 👀"
NOT_MEMBER_TEXT = "Голосовать могут только участники Берлоги 🦝"


def _cmd(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower()).rstrip("!?.")


def _is_admin(user_id: int) -> bool:
    return user_id in TGA_ADMINS


# ---------- отрисовка ----------

def _order(user_id: int, n: int) -> list[int]:
    """Свой порядок финалистов для каждого человека (против эффекта «первой кнопки»).

    random.Random со строковым seed детерминирован между запусками,
    поэтому у одного человека порядок в номинации всегда одинаковый.
    """
    idx = list(range(len(TGA_FINAL[n - 1].finalists)))
    random.Random(f"tga:{user_id}:{n}").shuffle(idx)
    return idx


def _bar(done: int, total: int, width: int = 10) -> str:
    filled = round(width * done / total) if total else 0
    return "▰" * filled + "▱" * (width - filled) + f" {done}/{total}"


def _cut(text: str) -> str:
    return text if len(text) <= BUTTON_MAX else text[: BUTTON_MAX - 1] + "…"


def _choice_label(n: int, choice: int | None) -> str:
    if choice is None:
        return "пропущено"
    finalists = TGA_FINAL[n - 1].finalists
    return finalists[choice].label if 0 <= choice < len(finalists) else "?"


def _needs_list(nom: Nomination) -> bool:
    return any(f.note or len(f.label) > LIST_IF_LONGER for f in nom.finalists)


def _first_unanswered(choices: dict[int, int | None]) -> int | None:
    return next((n for n in range(1, FINAL_COUNT + 1) if n not in choices), None)


def _next_after(n: int, choices: dict[int, int | None], mode: str) -> int | None:
    """Куда идти после ответа в номинации n. None — показать сводку."""
    if mode == "e":
        return None
    if mode == "r":
        return n + 1 if n < FINAL_COUNT else None
    # f: следующая без ответа после n, потом — пропущенные раньше
    for k in [*range(n + 1, FINAL_COUNT + 1), *range(1, n)]:
        if k not in choices:
            return k
    return None


def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def _nomination_view(
    user_id: int, n: int, choices: dict[int, int | None], mode: str
) -> tuple[str, InlineKeyboardMarkup]:
    nom = TGA_FINAL[n - 1]
    order = _order(user_id, n)
    answered = n in choices
    current = choices.get(n)

    lines = [
        "🗳 <b>Берлога Awards · финал</b>",
        _bar(len(choices), FINAL_COUNT),
        "",
        f"<i>{escape(nom.section)}</i>",
        f"<b>{n}. {escape(nom.title)}</b>",
        f"<i>{escape(nom.desc)}</i>",
    ]
    if _needs_list(nom):
        lines.append("")
        for i in order:
            f = nom.finalists[i]
            line = f"• <b>{escape(f.label)}</b>"
            if f.note:
                line += f" — {escape(f.note)}"
            lines.append(line)

    lines.append("")
    if not answered:
        lines.append("Выбери победителя 👇")
    elif current is None:
        lines.append("Сейчас: <b>пропущено</b>. Можно выбрать финалиста 👇")
    else:
        lines.append(f"✅ Твой голос: <b>{escape(_choice_label(n, current))}</b>. Можно поменять 👇")

    rows: list[list[InlineKeyboardButton]] = []
    for i in order:
        mark = "✅ " if answered and current == i else ""
        rows.append([_btn(_cut(mark + nom.finalists[i].label), f"tv:v:{n}:{i}:{mode}")])

    skip = _btn(("✅ " if answered and current is None else "") + "⏭ Пропустить", f"tv:s:{n}:{mode}")
    if mode == "e":
        rows.append([skip, _btn("📋 К сводке", "tv:sum")])
    else:
        nav: list[InlineKeyboardButton] = []
        if n > 1:
            nav.append(_btn("⬅️", f"tv:g:{n - 1}:{mode}"))
        nav.append(skip)
        if answered and n < FINAL_COUNT:  # вперёд — только если тут уже есть ответ
            nav.append(_btn("➡️", f"tv:g:{n + 1}:{mode}"))
        rows.append(nav)
        rows.append([_btn("📋 Мои голоса", "tv:sum")])

    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


def _summary_lines(choices: dict[int, int | None], header: str) -> list[str]:
    lines = [header, _bar(len(choices), FINAL_COUNT)]
    section = None
    for n, nom in enumerate(TGA_FINAL, start=1):
        if nom.section != section:
            section = nom.section
            lines += ["", f"<b>{escape(section)}</b>"]
        if n not in choices:
            value = "❔ <i>нет ответа</i>"
        elif choices[n] is None:
            value = "<i>пропущено</i>"
        else:
            value = escape(_choice_label(n, choices[n]))
        lines.append(f"{n}. {escape(nom.title)}: {value}")
    return lines


def _summary_view(
    choices: dict[int, int | None], header: str, *, editable: bool = True
) -> tuple[str, InlineKeyboardMarkup | None]:
    lines = _summary_lines(choices, header)
    if not editable:
        return "\n".join(lines), None

    lines += ["", "Чтобы поменять голос, нажми номер номинации 👇"]
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for n in range(1, FINAL_COUNT + 1):
        row.append(_btn(str(n) if n in choices else f"{n}❔", f"tv:g:{n}:e"))
        if len(row) == 5:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    first = _first_unanswered(choices)
    if first is not None:
        rows.append([_btn("▶️ Продолжить голосование", f"tv:g:{first}:f")])
    rows.append([_btn("✅ Готово", "tv:done")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


MY_VOTES_HEADER = "📋 <b>Твои голоса</b>"
FINISHED_HEADER = (
    "🎉 <b>Готово, спасибо за голос!</b>\n"
    "Итоги объявим на церемонии. Вот твои голоса:"
)


# ---------- проверки ----------

async def _is_member(bot: Bot, user_id: int) -> bool:
    if not TARGET_CHAT_ID:
        logger.error("TGA vote: TARGET_CHAT_ID не задан — проверить участника невозможно")
        return False
    try:
        m = await bot.get_chat_member(TARGET_CHAT_ID, user_id)
    except (TelegramBadRequest, TelegramForbiddenError, TelegramNotFound) as e:
        # «user not found» = не в чате. «chat not found»/Forbidden = неверный TARGET_CHAT_ID
        # или Монику убрали из чата — тогда это будет видно в логах.
        logger.warning("TGA vote: get_chat_member(%s, %s): %s", TARGET_CHAT_ID, user_id, e)
        return False
    except Exception:
        # Сетевой сбой / Telegram прилёг — не блокируем живых людей из-за чужой ошибки
        logger.exception("TGA vote: get_chat_member error, пропускаю проверку для %s", user_id)
        return True

    status = getattr(m.status, "value", m.status)  # в aiogram это enum, приводим к строке
    if status == "restricted":  # ограниченный в правах: проверяем, что он всё ещё в чате
        return bool(getattr(m, "is_member", False))
    return status in ("creator", "administrator", "member")


async def _show(cb: CallbackQuery, text: str, kb: InlineKeyboardMarkup | None) -> None:
    """Перерисовывает сообщение с кнопками; если редактировать нельзя — шлёт новое."""
    if isinstance(cb.message, Message):  # у старых сообщений бывает InaccessibleMessage
        try:
            await cb.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            return
        except TelegramBadRequest as e:
            if "message is not modified" in str(e).lower():
                return
            logger.warning("TGA vote: edit failed, sending new message: %s", e)
    await cb.bot.send_message(cb.from_user.id, text, reply_markup=kb, parse_mode="HTML")


# ---------- в группе: отправляем в ЛС ----------

@router.message(~PRIVATE, F.text.func(lambda t: _cmd(t) in ALL_COMMANDS))
async def vote_not_private(message: Message):
    me = await message.bot.me()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗳 Голосовать", url=f"https://t.me/{me.username}?start={DEEP_LINK_ARG}")
    ]])
    await message.reply("Голосование проходит у меня в личке, жми 👇", reply_markup=kb)


# ---------- старт ----------

async def _begin(message: Message, state: FSMContext, pool, how: str) -> None:
    """how: start — начать/продолжить, again — заново с 1-й, mine — сводка."""
    # Если человек завис в опросе 1 этапа — выводим из него, иначе следующие
    # его сообщения записались бы как номинанты. Прогресс опроса лежит в БД.
    await state.clear()

    user = message.from_user
    admin = _is_admin(user.id)
    vote_open = await tga_setting_get(pool, VOTE_OPEN)

    if not vote_open and not admin:
        voter = await vote_get_voter(pool, user.id)
        if how == "mine" and voter is not None:
            choices = await vote_get_choices(pool, user.id)
            text, _ = _summary_view(choices, MY_VOTES_HEADER + "\n🔒 Голосование закрыто", editable=False)
            await message.answer(text, parse_mode="HTML")
        else:
            await message.answer(CLOSED_TEXT)
        return

    if not await _is_member(message.bot, user.id):
        if admin:
            await message.answer(
                f"{NOT_MEMBER_TEXT}\n\n(для админа) Проверка участника не прошла: "
                f"TARGET_CHAT_ID={TARGET_CHAT_ID}. Подробности в логах контейнера."
            )
        else:
            await message.answer(NOT_MEMBER_TEXT)
        return

    await vote_start(pool, user.id, user.username, user.full_name)
    choices = await vote_get_choices(pool, user.id)

    if not vote_open:
        await message.answer(
            "🔒 Голосование закрыто для всех, но ты организатор — можешь проверить, как всё работает. "
            "Голоса записываются по-настоящему, их можно поменять в любой момент."
        )

    if how == "mine":
        text, kb = _summary_view(choices, MY_VOTES_HEADER)
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    if how == "again":
        await message.answer(
            "Проходим все номинации заново 🔁\n"
            "Прошлые голоса отмечены ✅: нажми их ещё раз, чтобы оставить, или выбери другого."
        )
        text, kb = _nomination_view(user.id, 1, choices, "r")
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    first = _first_unanswered(choices)
    if first is None:
        text, kb = _summary_view(
            choices,
            MY_VOTES_HEADER + "\nОтвет есть во всех номинациях ✅ Поменять можно кнопками ниже "
            "или пройти всё заново: «моника голосование заново».",
        )
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    if not choices:
        await message.answer(INTRO_TEXT, parse_mode="HTML")
    else:
        await message.answer(f"Продолжаем с номинации {first}/{FINAL_COUNT} 👌")
    text, kb = _nomination_view(user.id, first, choices, "f")
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(PRIVATE, F.text.func(lambda t: _cmd(t) in START_COMMANDS))
async def vote_begin(message: Message, state: FSMContext, pool):
    await _begin(message, state, pool, "start")


@router.message(PRIVATE, F.text.func(lambda t: _cmd(t) in AGAIN_COMMANDS))
async def vote_again(message: Message, state: FSMContext, pool):
    await _begin(message, state, pool, "again")


@router.message(PRIVATE, F.text.func(lambda t: _cmd(t) in MINE_COMMANDS))
async def vote_mine(message: Message, state: FSMContext, pool):
    await _begin(message, state, pool, "mine")


async def vote_deeplink(message: Message, state: FSMContext, pool):
    await _begin(message, state, pool, "start")


def register_vote_deeplink(dp: Dispatcher) -> None:
    """Ссылка t.me/<бот>?start=vote приходит боту как «/start vote».

    Регистрируем её прямо в диспетчере и ДО приветствия Моники: хендлеры самого
    диспетчера проверяются раньше роутеров, и приветствие (Command("start"))
    иначе перехватило бы ссылку. Обычный /start без «vote» сюда не попадает.
    """
    dp.message.register(
        vote_deeplink,
        PRIVATE,
        CommandStart(deep_link=True, magic=F.args == DEEP_LINK_ARG),
    )


# ---------- кнопки ----------

@router.callback_query(F.data.startswith("tv:"))
async def vote_callback(cb: CallbackQuery, pool):
    user_id = cb.from_user.id

    if not _is_admin(user_id) and not await tga_setting_get(pool, VOTE_OPEN):
        await cb.answer("Голосование закрыто 🔒", show_alert=True)
        return

    # Строка в tga_voters появляется только после проверки участника в _begin
    before = await vote_get_voter(pool, user_id)
    if before is None:
        await cb.answer("Сначала напиши мне «моника голосование»", show_alert=True)
        return

    parts = (cb.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""

    if action == "sum":
        choices = await vote_get_choices(pool, user_id)
        await cb.answer()
        await _show(cb, *_summary_view(choices, MY_VOTES_HEADER))
        return

    if action == "done":
        choices = await vote_get_choices(pool, user_id)
        lines = _summary_lines(choices, MY_VOTES_HEADER)
        lines += ["", "Спасибо! 🦝 Поменять голоса можно до конца голосования: «моника мои голоса»."]
        await cb.answer()
        await _show(cb, "\n".join(lines), None)
        return

    try:
        n = int(parts[2])
        if not 1 <= n <= FINAL_COUNT:
            raise ValueError
        if action == "v":
            choice: int | None = int(parts[3])
            mode = parts[4]
            if not 0 <= choice < len(TGA_FINAL[n - 1].finalists):
                raise ValueError
        elif action in ("s", "g"):
            choice = None
            mode = parts[3]
        else:
            raise ValueError
        if mode not in MODES:
            raise ValueError
    except (IndexError, ValueError):
        await cb.answer("Кнопка устарела, напиши «моника голосование»", show_alert=True)
        return

    if action == "g":  # листание: ничего не записываем
        choices = await vote_get_choices(pool, user_id)
        await cb.answer()
        await _show(cb, *_nomination_view(user_id, n, choices, mode))
        return

    try:
        after = await vote_save(pool, user_id, n, choice, FINAL_COUNT)
    except Exception:
        logger.exception("TGA vote: save failed user=%s n=%s", user_id, n)
        await cb.answer("Не смогла сохранить голос… попробуй ещё раз", show_alert=True)
        return

    await cb.answer("Пропущено" if choice is None else "Голос записан ✅")

    choices = await vote_get_choices(pool, user_id)
    just_finished = before["completed_at"] is None and after["completed_at"] is not None
    nxt = _next_after(n, choices, mode)

    if just_finished:
        await _show(cb, *_summary_view(choices, FINISHED_HEADER))
    elif nxt is None:
        await _show(cb, *_summary_view(choices, MY_VOTES_HEADER))
    else:
        await _show(cb, *_nomination_view(user_id, nxt, choices, mode))
