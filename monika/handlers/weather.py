import aiohttp
from aiogram import Router, types
from common.utils.links import get_bot
from cfg import WEATHER_API_KEY

router = Router()

PREFIX = "погода"


async def weatherapi_get(session: aiohttp.ClientSession, endpoint: str, params: dict):
    url = f"https://api.weatherapi.com/v1/{endpoint}"

    async with session.get(url, params=params) as resp:
        print("---- WEATHERAPI CALL ----")
        print("Endpoint:", endpoint)
        print("Final URL:", str(resp.url))
        print("Status:", resp.status)
        print("Server header:", resp.headers.get("Server"))

        try:
            data = await resp.json(content_type=None)
        except Exception:
            text = await resp.text()
            print("Invalid JSON response:", text)
            return resp.status, None

        print("Response body:", data)
        print("-------------------------\n")

        return resp.status, data


async def get_weather(city: str):
    async with aiohttp.ClientSession() as session:

        test_status, test_data = await weatherapi_get(
            session,
            "forecast.json",
            {
                "key": WEATHER_API_KEY,
                "q": "48.8567,2.3508",
                "days": 1,
                "lang": "ru",
            },
        )

        print("COORD TEST RESULT:", test_status)

        status, search_data = await weatherapi_get(
            session,
            "search.json",
            {
                "key": WEATHER_API_KEY,
                "q": city,
            },
        )

        if status != 200:
            print("Search request failed")
            return None

        if not isinstance(search_data, list) or not search_data:
            print("Search returned empty list for:", repr(city))
            return None

        loc = search_data[0]
        loc_id = loc.get("id")

        if not loc_id:
            print("Search result missing id:", loc)
            return None

        # 3) forecast по ID
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
            print("Forecast by ID failed")
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