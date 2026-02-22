import aiohttp
from aiogram import Router, types
from common.utils.links import get_bot
from cfg import WEATHER_API_KEY

router = Router()

PREFIX = "погода"


async def weatherapi_get(session: aiohttp.ClientSession, endpoint: str, params: dict):
    url = f"https://api.weatherapi.com/v1/{endpoint}"
    async with session.get(url, params=params) as resp:
        data = await resp.json(content_type=None)
        return resp.status, data


async def get_weather(city: str):
    async with aiohttp.ClientSession() as session:
        status, search_data = await weatherapi_get(
            session,
            "search.json",
            {"key": WEATHER_API_KEY, "q": city, "lang": "ru"},
        )

        print("SEARCH status:", status)
        print("SEARCH body type:", type(search_data))
        print("SEARCH body:", search_data[:3] if isinstance(search_data, list) else search_data)

        if not isinstance(search_data, list) or not search_data:
            print("SEARCH: no results for:", repr(city))
            return None

        if status != 200:
            print("WeatherAPI search error:", status, search_data)
            return None

        loc = search_data[0]
        loc_id = loc.get("id")
        if not loc_id:
            print("WeatherAPI search: missing id:", loc)
            return None

        status, forecast_data = await weatherapi_get(
            session,
            "forecast.json",
            {
                "key": WEATHER_API_KEY,
                "q": f"id:{loc_id}",
                "days": 2,
                "lang": "ru",
            },
        )

        if status != 200:
            print("WeatherAPI forecast error:", status, forecast_data)
            return None

        return forecast_data


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