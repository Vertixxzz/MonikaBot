from aiogram import Dispatcher
from .handlers.greetings import register_greetings
from monika.handlers.remember import router as remember_router
from monika.handlers.weather import router as weather_router
from monika.handlers.spam import router as spam_router
from monika.handlers.antiiris import router as antiiris_router
from monika.handlers.silence import router as silence_router
from monika.handlers.warn import router as warn_router

def register_monika_middlewares(dp: Dispatcher):
    pass

def register_monika_handlers(dp: Dispatcher):
    register_greetings(dp)
    dp.include_router(warn_router)
    dp.include_router(remember_router)
    #dp.include_router(weather_router)
    #dp.include_router(spam_router)
    dp.include_router(antiiris_router)
    dp.include_router(silence_router)
    print("📌 Подключаем warn_router")