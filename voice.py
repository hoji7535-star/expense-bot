"""
voice.py — Telegram ovozli xabarlarni (.ogg) matnga aylantirish.

ffmpeg yordamida .ogg -> .wav ga konvertatsiya qilinadi, so'ngra
SpeechRecognition kutubxonasi (Google Web Speech API, bepul, internet talab
qiladi) orqali matnga o'giriladi. Til: o'zbekcha (uz-UZ), agar tanilmasa
ruscha (ru-RU) bilan qayta urinib ko'riladi.
"""
import os
import subprocess
import tempfile
import speech_recognition as sr

recognizer = sr.Recognizer()


def convert_ogg_to_wav(ogg_path: str) -> str:
    wav_path = ogg_path.rsplit(".", 1)[0] + ".wav"
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", ogg_path, "-ar", "16000", "-ac", "1", wav_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg xatosi: {result.stderr.decode(errors='ignore')}")
    return wav_path


def transcribe(ogg_path: str) -> str:
    """Ovozli faylni matnga o'giradi. Muvaffaqiyatsiz bo'lsa bo'sh string qaytaradi."""
    wav_path = convert_ogg_to_wav(ogg_path)
    try:
        with sr.AudioFile(wav_path) as source:
            audio = recognizer.record(source)
        for lang in ("uz-UZ", "ru-RU"):
            try:
                text = recognizer.recognize_google(audio, language=lang)
                if text:
                    return text
            except sr.UnknownValueError:
                continue
            except sr.RequestError:
                break
        return ""
    finally:
        if os.path.exists(wav_path):
            os.remove(wav_path)
