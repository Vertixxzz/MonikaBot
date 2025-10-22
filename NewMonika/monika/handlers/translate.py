from aiogram import Router, F
from aiogram.types import Message
from deep_translator import GoogleTranslator

router = Router()

ALIASES = {
    "англ": "en", "ен": "en",
    "рус": "ru",  "ру": "ru",
    "яп": "ja",   "кит": "zh-cn",
    "py": "ru",   # если хочешь поддержать 'py' как 'ru'
}

def normalize_lang(tok: str) -> str:
    t = (tok or "").lower()
    return ALIASES.get(t, t)

PREFIX = "моника переведи"

@router.message(F.text.func(lambda t: t and t.lower().startswith(PREFIX)))
async def translate_handler(message: Message):
    text = (message.text or "")
    rest = text[len(PREFIX):].strip()          # всё после "моника переведи"

    if not rest:
        await message.reply("Укажи язык и текст. Пример: моника переведи en Привет!")
        return

    # отделяем язык и остальной текст
    lang_and_text = rest.split(maxsplit=1)
    target_lang = normalize_lang(lang_and_text[0])
    inline_text = lang_and_text[1] if len(lang_and_text) > 1 else None

    # если команда как reply — берём текст из исходного сообщения
    if message.reply_to_message:
        source_text = message.reply_to_message.text or message.reply_to_message.caption
    else:
        source_text = inline_text

    if not source_text:
        await message.reply("После языка напиши текст для перевода.")
        return

    try:
        translated = GoogleTranslator(source='auto', target=target_lang).translate(source_text)
        await message.reply(translated or "Не получилось перевести текст.")
    except Exception as e:
        await message.reply(f"Ошибка перевода: {e}")

