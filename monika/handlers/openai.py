from aiogram import Router, types
import openai
from cfg import OPENAI_API_KEY, VIP_USERS

router = Router()
openai.api_key = OPENAI_API_KEY

BOT_CONTEXT = [
    {"role": "system", "content": "Ты - Моника. Старшеклассница, отличные оценки, у тебя есть свой литературный клуб. Ты поддерживаешь физическую форму"},
    {"role": "system", "content": "У тебя был опыт в дебатах, но они тебе не понравились так как вокруг слишком много драмы и сплетен"},
    {"role": "system", "content": "В твоем литературном клубе есть еще 3 девочки - Сайори, Юри и Нацуки"},
]

MEMORY = []

@router.message(lambda m: m.text and m.text.lower().startswith("моника суперзапомни"))
async def monika_remember(message: types.Message):
    user_id = message.from_user.id
    if user_id not in VIP_USERS:
        await message.reply("Увы, ты не в белом листе моих ИИ функций")
    info = message.text[len("моника суперзапомни"):].strip()
    if not info:
        await message.reply("Что именно мне запомнить?")
        return
    MEMORY.append(info)
    await message.reply(f"Хорошо, запомнила: {info}")

@router.message(lambda message: message.text and message.text.lower().startswith("моника ии"))
async def monika_ai_handler(message: types.Message):
    user_query = message.text[len("моника ии"):].strip()
    if not user_query:
        await message.reply("Что ты хочешь спросить? Напиши после 'моника ии' свой вопрос.")
        return

    user_id = message.from_user.id
    if user_id not in VIP_USERS:
        await message.reply("Увы, ты не в белом листе моих ИИ функций")
        return

    memory_context = [
        {"role": "system", "content": f"{m}"}
        for m in MEMORY
    ]

    messages = BOT_CONTEXT + memory_context + [{"role": "user", "content": user_query}]

    try:
        completion = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            temperature=0.8,
            max_tokens=500,
        )
        reply = completion.choices[0].message["content"].strip()
        await message.reply(reply)
    except Exception as e:
        await message.answer("Произошла ошибка при обращении к серверам OpenAI.")
        print(f"Иишка слетела:{e}")
