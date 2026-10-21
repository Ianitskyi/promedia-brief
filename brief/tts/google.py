"""Google Cloud Text-to-Speech, Chirp 3: HD voices (uk-UA is supported).

Price (cloud.google.com/text-to-speech/pricing, checked 2026-10-20): US$30 per 1M
characters after 1M free characters per month. Custom pronunciations are NOT
available for uk-UA in Chirp 3: HD, so the lexicon is applied as plain text.
Credentials: GOOGLE_APPLICATION_CREDENTIALS (service account JSON), as in the
existing render-audio workflow.
"""
import os

from . import register
from .base import Provider, TTSError


@register
class GoogleChirpProvider(Provider):
    name = "google"
    paid = True
    price_per_million = 30.0
    free_chars_per_month = 1_000_000
    max_chars = 4800  # API limit is 5000 bytes of input
    measure_bytes = True
    default_voice = "uk-UA-Chirp3-HD-Kore"

    def synthesize(self, text, out_path):
        try:
            from google.cloud import texttospeech
        except ImportError as e:
            raise TTSError("pip install google-cloud-texttospeech") from e
        if len(text.encode("utf-8")) > 4800:
            raise TTSError("google: chunk exceeds 5000-byte request limit")
        client = texttospeech.TextToSpeechClient()
        resp = client.synthesize_speech(request={
            "input": texttospeech.SynthesisInput(text=text),
            "voice": texttospeech.VoiceSelectionParams(language_code="uk-UA", name=self.voice),
            "audio_config": texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.MP3,
                speaking_rate=float(os.environ.get("BRIEF_SPEAKING_RATE", "1.0")),
            ),
        })
        if not resp.audio_content:
            raise TTSError("google: empty audio")
        with open(out_path, "wb") as f:
            f.write(resp.audio_content)
        return out_path
