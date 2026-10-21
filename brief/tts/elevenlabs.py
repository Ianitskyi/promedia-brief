"""ElevenLabs (eleven_multilingual_v2 supports Ukrainian). Ported from api/tts.js.

Price (elevenlabs.io/pricing/api, checked 2026-10-20): Multilingual v2/v3 US$0.08
per 1K characters (= US$80 / 1M) on pay-as-you-go; subscription plans include
character quotas (Starter $6/mo: 75K chars). Env: ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID.
"""
import json
import os

from .. import http
from . import register
from .base import Provider, TTSError


@register
class ElevenLabsProvider(Provider):
    name = "elevenlabs"
    paid = True
    price_per_million = 80.0
    max_chars = 4500
    default_voice = None

    def synthesize(self, text, out_path):
        key = self.env("ELEVENLABS_API_KEY")
        voice = self.voice or self.env("ELEVENLABS_VOICE_ID")
        body = {"text": text, "model_id": os.environ.get("BRIEF_ELEVENLABS_MODEL", "eleven_multilingual_v2"),
                "voice_settings": {"stability": 0.7, "similarity_boost": 0.75, "style": 0.0,
                                   "use_speaker_boost": True}}
        try:
            audio = http.fetch(f"https://api.elevenlabs.io/v1/text-to-speech/{voice}?output_format=mp3_44100_128",
                               data=json.dumps(body).encode(), retries=2, max_bytes=50_000_000,
                               headers={"xi-api-key": key, "Content-Type": "application/json"})
        except http.FetchError as e:
            raise TTSError(f"elevenlabs: {e}") from e
        with open(out_path, "wb") as f:
            f.write(audio)
        return out_path
