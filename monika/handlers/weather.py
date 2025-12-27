import aiohttp
from aiogram import Router, types
from common.utils.links import get_bot
from cfg import WEATHER_API_KEY

router = Router()

async def get_weather(city: str):
    async with aiohttp.ClientSession() as session:
        url = (
            f"http://api.weatherapi.com/v1/forecast.json"
            f"?key={WEATHER_API_KEY}&q={city}&days=2&lang=ru"
        )
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            return await resp.json()

PREFIXES = ("моника погода", "погода")

@router.message(lambda msg: msg.text and msg.text.lower().startswith(PREFIXES))
async def handle_weather(message: types.Message):
    text = message.text.strip()
    low = text.lower()

    for p in PREFIXES:
        if low.startswith(p):
            city = text[len(p):].strip()   # всё после префикса
            break

    if not city:
        await message.answer("Напиши город: `погода Москва` или `Моника погода Астана`")
        return

    data = await get_weather(city)
    if not data:
        await message.reply("Такого города не существует", parse_mode="Markdown")
        return

    location = data["location"]["name"]
    current = data["current"]
    forecast = data["forecast"]["forecastday"][1]["day"]

    comment = "Капец у вас жарко.." if current["temp_c"] > 25 else ""

    response = (
        f"Погода в *{location}*\n"
        f"Сейчас: *{current['temp_c']}°C* (ощущается как *{current['feelslike_c']}°C*)\n"
        f"{current['condition']['text']}\n"
        f"Ветер: {current['wind_kph']} км/ч\n"
        f"Влажность: {current['humidity']}%\n\n"
        f"*Прогноз на завтра:*\n"
        f"Днём: *{forecast['avgtemp_c']}°C*, осадки: *{forecast['daily_chance_of_rain']}%*\n"
      f"{forecast['condition']['text']}\n"
        f"{comment}"
    )
    await message.reply(response, parse_mode="Markdown")

    if current["temp_c"] < -5:
        sayori = get_bot("sayori")
        if sayori:
            try:
                await sayori.send_message(message.chat.id, "ужас как холодно...")
            except Exception as e:
                print("Ошибка при сообщении Сайори:", e)