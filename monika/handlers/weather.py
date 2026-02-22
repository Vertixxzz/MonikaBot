import aiohttp
from aiogram import Router, types
from common.utils.links import get_bot
from cfg import WEATHER_API_KEY

router = Router()

PREFIX = "погода"


async def get_weather(city: str):
    url = "https://api.weatherapi.com/v1/forecast.json"

    params = {
        "key": WEATHER_API_KEY,
        "q": city,
        "days": 2,
        "lang": "ru",
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            data = await resp.json()

            if resp.status != 200:
                print("WeatherAPI error:", data)
                return None

            if "error" in data:
                print("WeatherAPI returned error:", data)
                return None

            return data


@router.message(lambda msg: msg.text and msg.text.lower().startswith(PREFIX))
async def handle_weather(message: types.Message):
    text = message.text.strip()
    city = text[len(PREFIX):].strip()

    if not city:
        await message.answer("Напиши город: `погода Москва`", parse_mode="Markdown")
        return

    data = await get_weather(city)

    if not data:
        await message.reply("Такого города не существует", parse_mode="Markdown")
        return

    location = data["location"]["name"]
    region = data["location"].get("region")
    country = data["location"].get("country")

    current = data["current"]
    forecast = data["forecast"]["forecastday"][1]["day"]

    comment = "Капец у вас жарко.." if current["temp_c"] > 25 else ""

    location_line = location
    if region and region != location:
        location_line += f", {region}"
    if country:
        location_line += f", {country}"

    response = (
        f"Погода в *{location_line}*\n"
        f"Сейчас: *{current['temp_c']}°C* "
        f"(ощущается как *{current['feelslike_c']}°C*)\n"
        f"{current['condition']['text']}\n"
        f"Ветер: {current['wind_kph']} км/ч\n"
        f"Влажность: {current['humidity']}%\n\n"
        f"*Прогноз на завтра:*\n"
        f"Днём: *{forecast['avgtemp_c']}°C*, "
        f"осадки: *{forecast['daily_chance_of_rain']}%*\n"
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