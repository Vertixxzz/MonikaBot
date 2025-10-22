import aiohttp
from aiogram import Router, types

router = Router()

WEATHER_API_KEY = "ccf1d2a873dc44d7937123420252905"

async def get_weather(city: str) -> str:
    async with aiohttp.ClientSession() as session:
        url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={city}&days=2&lang=ru"
        async with session.get(url) as resp:
            if resp.status != 200:
                return "Такого города не существует"

            data = await resp.json()

            location = data["location"]["name"]
            current = data["current"]
            forecast = data["forecast"]["forecastday"][1]["day"]  # Завтра
            comment = ""
            if current["temp_c"] > 25:
                comment = "Капец у вас жарко.."

            response = (
                f"Погода в *{location}*\n"
                f"Сейчас: *{current['temp_c']}°C* (ощущается как *{current['feelslike_c']}°C*)\n"
                f"{current['condition']['text']}\n"
                f"Ветер: {current['wind_kph']} км/ч\n"
                f"Влажность: {current['humidity']}%\n\n"
                f"*Прогноз на завтра:*\n"
                f"Днём: *{forecast['avgtemp_c']}°C*, "
                f"осадки: *{forecast['daily_chance_of_rain']}%*\n"
                f"{forecast['condition']['text']}\n"
                f"{comment}"
            )

            return response

@router.message(lambda msg: msg.text and msg.text.lower().startswith("моника погода "))
async def handle_weather(message: types.Message):
    city = message.text[len("моника погода "):].strip()
    if not city:
        await message.reply("Я не вижу этот город", parse_mode="Markdown")
        return

    get_weather

    weather_report = await get_weather(city)

    await message.reply(weather_report, parse_mode="Markdown")
