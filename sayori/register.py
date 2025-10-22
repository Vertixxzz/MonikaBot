from .handlers.clouds import register_clouds
from .handlers.greetings import register_greetings
from aiogram import Dispatcher

def register_sayori_middlewares(dp: Dispatcher):
    pass

def register_sayori_handlers(dp: Dispatcher):
    register_greetings(dp)
    register_clouds(dp)
