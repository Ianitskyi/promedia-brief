"""ElevenLabs. Ukrainian is supported by eleven_v3, eleven_v4, eleven_multilingual_v2 and
eleven_flash_v2_5 (elevenlabs.io/docs/overview/models, checked 2026-10-22).

Model: BRIEF_ELEVENLABS_MODEL (default eleven_v3). eleven_v3 understands audio tags such as
[sympathetic] or [warmly]; they set the tone of a story and are not spoken (the ASR check
catches it if one is). Price: about 1 credit per character on subscription plans
(Starter ≈ $6/month for 30K credits); pay-as-you-go ≈ US$0.08 per 1K characters, which is
what the cost guard assumes. Env: ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID.
"""
import json
import os

from .. import http
from . import register
from .base import Provider, TTSError

TAG_MODELS = ("eleven_v3",)
LANGUAGE_CODE_MODELS = ("eleven_v3", "eleven_flash_v2_5", "eleven_turbo_v2_5")


def model():
    return os.environ.get("BRIEF_ELEVENLABS_MODEL", "eleven_v3")


@register
class ElevenLabsProvider(Provider):
    name = "elevenlabs"
    paid = True
    price_per_million = 80.0
    max_chars = 4500
    default_voice = None
    # Numbers are spelled out by brief.speech with Ukrainian case agreement («двадцять першого
    # жовтня», «п'ятнадцятирічних»): ElevenLabs' own reading of digits got the cases wrong.
    spell_digits = True

    @property
    def auto_stress(self):
        """BRIEF_ELEVENLABS_STRESS=1: stress marks on every word from the Ukrainian stress dictionary."""
        return os.environ.get("BRIEF_ELEVENLABS_STRESS", "0") == "1"

    @property
    def audio_tags(self):
        return model() in TAG_MODELS

    def describe(self):
        return {**super().describe(), "model": model()}

    def synthesize(self, text, out_path):
        key = self.env("ELEVENLABS_API_KEY")
        voice = self.voice or self.env("ELEVENLABS_VOICE_ID")
        m = model()
        if m == "eleven_v3":
            settings = {"stability": float(os.environ.get("BRIEF_ELEVENLABS_STABILITY", "0.5"))}
        else:
            settings = {"stability": 0.7, "similarity_boost": 0.75, "style": 0.0, "use_speaker_boost": True}
        body = {"text": text, "model_id": m, "voice_settings": settings}
        if m in LANGUAGE_CODE_MODELS:
            body["language_code"] = "uk"
        try:
            audio = http.fetch(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
                               data=json.dumps(body).encode(), retries=2, max_bytes=50_000_000,
                               headers={"xi-api-key": key, "Content-Type": "application/json"})
        except http.FetchError as e:
            raise TTSError(f"elevenlabs: {e}") from e
        with open(out_path, "wb") as f:
            f.write(audio)
        return out_path
