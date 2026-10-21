"""OpenAI speech API (gpt-4o-mini-tts or tts-1-hd).

Price (developers.openai.com/api/docs/pricing, checked 2026-10-20): tts-1 US$15 /
1M chars, tts-1-hd US$30 / 1M chars; gpt-4o-mini-tts US$0.60 / 1M text tokens +
US$12 / 1M audio tokens. Voices are multilingual, not Ukrainian-native — accent
must be checked by listening. `instructions` asks for verbatim neutral reading,
but a model-based voice can still deviate; the ASR check in render.py catches that.
Env: OPENAI_API_KEY.
"""
import json
import os

from .. import http
from . import register
from .base import Provider, TTSError

INSTRUCTIONS = ("Read the Ukrainian text exactly as written, word for word, in a calm neutral news-anchor voice. "
                "Do not add, skip or change any words. No emotion, no emphasis beyond normal news reading.")


@register
class OpenAIProvider(Provider):
    name = "openai"
    paid = True
    price_per_million = 15.0  # tts-1 per char; gpt-4o-mini-tts is token-billed (≈ similar order), see docs/TTS.md
    max_chars = 4000
    default_voice = "alloy"

    def synthesize(self, text, out_path):
        key = self.env("OPENAI_API_KEY")
        model = os.environ.get("BRIEF_OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
        body = {"model": model, "voice": self.voice, "input": text, "response_format": "mp3"}
        if model.startswith("gpt-"):
            body["instructions"] = INSTRUCTIONS
        try:
            audio = http.fetch("https://api.openai.com/v1/audio/speech", data=json.dumps(body).encode(), retries=2,
                               max_bytes=50_000_000,
                               headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        except http.FetchError as e:
            raise TTSError(f"openai: {e}") from e
        with open(out_path, "wb") as f:
            f.write(audio)
        return out_path
