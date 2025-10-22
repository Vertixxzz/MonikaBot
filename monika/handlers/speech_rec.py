import re
import random
import subprocess
import wave
import json
import os

from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from vosk import Model, KaldiRecognizer
from cfg import *
import ffmpeg

router = Router()

MODEL = "NewMonika/common/sttmodel/vosk-model-small-ru-0.22"
model = Model(MODEL)

async def recognition(file_path):
    wav_path = file_path.replace(".ogg", ".wav")
    subprocess.run(["ffmpeg", "-i", file_path, "-ar", "16000", "-ac", "1", wav_path, "-y"], check=True)

    wf = wave.open(wav_path, "rb")
    rec = KaldiRecognizer(model, wf.getframerate())

    result_text = ""
    while True:
        data = wf.readframes(4000)
        if len(data) == 0:
            break
        if rec.AcceptWaveform(data):
            res = json.loads(rec.Result())
            result_text += res.get("text", "") + " "

    res = json.loads(rec.FinalResult())
    result_text += res.get("text", "")
    return result_text.strip()

@router.message(F.text.regexp(r"(?i)^моника расшифруй$"))
async def handle_voice(message: Message, bot: Bot):
    if message.reply_to_message and message.reply_to_message.voice:
        file = await bot.get_file(message.reply_to_message.voice.file_id)
        ogg_path = f"voice_{message.from_user.id}.ogg"
        await bot.download_file(file.file_path, ogg_path)
        original_user = message.reply_to_message.from_user
        username = original_user.username or original_user.first_name
        text = await recognition(ogg_path)

        if text == "":
            await message.answer("Я не смогла услышать слова в этом голосовом")
            return

        await message.answer(f"@{username if original_user.username else username} сказал: {text}")

        os.remove(ogg_path)
        wav_path = ogg_path.replace(".ogg", ".wav")
        if os.path.exists(wav_path):
            os.remove(wav_path)
    else:
        await message.answer("Пришли это в ответ на голосовое")