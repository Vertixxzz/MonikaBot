import re
import unicodedata
import aiohttp
from aiogram import Router, types
from common.utils.links import get_bot
from cfg import WEATHER_API_KEY

router = Router()

PREFIXES = ("моника погода", "погода")

ZERO_WIDTH = {
    "\u200b", "\u200c", "\u200d", "\u2060", "\ufeff",
    "\u200e", "\u200f", "\u202a", "\u202b", "\u202c",
    "\u202d", "\u202e",
}

def sanitize_city(raw: str) -> str:
    s = " ".join(raw.split())

    s = "".join(
        ch for ch in s
        if ch not in ZERO_WIDTH and unicodedata.category(ch) != "Cf"
    )

    s = s.strip(" \t\n\r,.;:!?\"'()[]{}<>«»`~")

    s = re.sub(r"^(город|г\.|city)\s*[:\-]?\s*", "", s, flags=re.IGNORECASE)

    s = re.sub(r"[^0-9A-Za-zА-Яа-яЁёІіЇїЄєҐґӨөҚқҢңҮүҰұҺһӘә\s\-,.]", "", s)

    return s.strip(" ,.-")


async def get_weather(city: str):
    async with aiohttp.ClientSession() as session:
        url = "https://api.weatherapi.com/v1/forecast.json"
        params = {
            "key": WEATHER_API_KEY,
            "q": city,
            "days": 2,
            "lang": "ru",
        }

        async with session.get(url, params=params) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                text = await resp.text()
                print("WeatherAPI invalid JSON:", resp.status, text)
                return None

            if resp.status != 200:
                err = data.get("error", {})
                print("WeatherAPI error:", resp.status, err)

                if err.get("code") == 1006:
                    return None

                return None

            return data


@router.message(lambda msg: msg.text and msg.text.lower().startswith(PREFIXES))
async def handle_weather(message: types.Message):
    text = message.text.strip()
    low = text.lower()

    city_raw = ""
    for p in PREFIXES:
        if low.startswith(p):
            city_raw = text[len(p):].strip()
            break

    city = sanitize_city(city_raw)

    print("RAW city repr:", repr(city))
    print("RAW codepoints:", [hex(ord(ch)) for ch in city])

    if not city:
        await message.answer(
            "Напиши город: `погода Москва` или `Моника погода Астана`",
            parse_mode="Markdown"
        )
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

    location_line = f"{location}"
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
                await sayori.send_message(
                    message.chat.id,
                    "ужас как холодно..."
                )
            except Exception as e:
                print("Ошибка при сообщении Сайори:", e)