import re
import aiohttp
from aiogram import Router, types
from common.utils.links import get_bot
from cfg import WEATHER_API_KEY

router = Router()

PREFIXES = ("моника погода", "погода")

def normalize_city(raw: str) -> str:
    s = " ".join(raw.split())

    s = s.strip(" \t\n\r,.;:!?\"'()[]{}<>«»`~")

    s = re.sub(r"^(город|г\.|city)\s*[:\-]?\s*", "", s, flags=re.IGNORECASE)

    return s

def pick_best_location(query: str, locations: list[dict]) -> dict | None:
    if not locations:
        return None

    q = query.casefold()

    def score(loc: dict) -> int:
        name = (loc.get("name") or "").casefold()
        region = (loc.get("region") or "").casefold()
        country = (loc.get("country") or "").casefold()

        if name == q:
            return 100
        if f"{name}, {country}" == q or f"{name}, {region}" == q:
            return 95

        if name.startswith(q):
            return 80
        if q in name:
            return 70

        first = q.split()[0] if q.split() else q
        if first and name == first:
            return 85
        if first and name.startswith(first):
            return 75

        # слабые сигналы
        if q in f"{name} {region} {country}":
            return 50

        return 0

    best = max(locations, key=score)
    return best if score(best) > 0 else locations[0]

async def weatherapi_get(session: aiohttp.ClientSession, path: str, params: dict):
    url = f"https://api.weatherapi.com/v1/{path}"
    async with session.get(url, params=params) as resp:
        data = await resp.json(content_type=None)
        return resp.status, data

async def resolve_city_to_latlon(session: aiohttp.ClientSession, city: str) -> tuple[float, float] | None:
    status, data = await weatherapi_get(
        session,
        "search.json",
        {"key": WEATHER_API_KEY, "q": city, "lang": "ru"},
    )
    if status != 200:
        print("WeatherAPI search error:", status, data)
        return None

    best = pick_best_location(city, data if isinstance(data, list) else [])
    if not best:
        return None

    lat = best.get("lat")
    lon = best.get("lon")
    if lat is None or lon is None:
        return None

    return float(lat), float(lon)

async def get_weather_by_city(city: str):
    async with aiohttp.ClientSession() as session:
        latlon = await resolve_city_to_latlon(session, city)
        if not latlon:
            return None

        lat, lon = latlon
        status, data = await weatherapi_get(
            session,
            "forecast.json",
            {
                "key": WEATHER_API_KEY,
                "q": f"{lat},{lon}",
                "days": 2,
                "lang": "ru",
            },
        )
        if status != 200:
            print("WeatherAPI forecast error:", status, data)
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

    city = normalize_city(city_raw)

    if not city:
        await message.answer("Напиши город: `погода Москва` или `Моника погода Астана`")
        return

    data = await get_weather_by_city(city)
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