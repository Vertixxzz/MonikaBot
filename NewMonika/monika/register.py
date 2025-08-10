from aiogram import Dispatcher
from .handlers.greetings import register_greetings
from NewMonika.monika.handlers.remember import router as remember_router
from NewMonika.monika.handlers.weather import router as weather_router
from NewMonika.monika.handlers.spam import router as spam_router
from NewMonika.monika.handlers.antiiris import router as antiiris_router
from NewMonika.monika.handlers.silence import router as silence_router
from NewMonika.monika.handlers.warn import router as warn_router
from NewMonika.monika.handlers.ecomoniks import router as ec_router
from NewMonika.monika.handlers.speech_rec import router as sr_router

def register_monika_middlewares(dp: Dispatcher):
    pass

def register_monika_handlers(dp: Dispatcher):
    register_greetings(dp)
    dp.include_router(ec_router)
    dp.include_router(warn_router)
    dp.include_router(remember_router)
    dp.include_router(antiiris_router)
    dp.include_router(silence_router)
    # dp.include_router(sr_router)