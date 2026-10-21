"""Azure AI Speech, neural voices uk-UA-PolinaNeural / uk-UA-OstapNeural.

Price (Azure retail prices API, westeurope, checked 2026-10-20): Neural TTS US$15
per 1M characters; free tier F0 0.5M characters/month. SSML allows explicit
pauses and <sub alias> substitutions. Env: AZURE_SPEECH_KEY, AZURE_SPEECH_REGION.
"""
from xml.sax.saxutils import escape

from .. import http
from . import register
from .base import Provider, TTSError


@register
class AzureProvider(Provider):
    name = "azure"
    paid = True
    price_per_million = 15.0
    free_chars_per_month = 500_000
    max_chars = 3000
    default_voice = "uk-UA-PolinaNeural"

    def synthesize(self, text, out_path):
        key, region = self.env("AZURE_SPEECH_KEY"), self.env("AZURE_SPEECH_REGION")
        ssml = (f'<speak version="1.0" xml:lang="uk-UA"><voice name="{escape(self.voice)}">'
                f"{escape(text)}</voice></speak>")
        try:
            audio = http.fetch(
                f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                data=ssml.encode("utf-8"), retries=2, max_bytes=50_000_000,
                headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                         "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3"},
            )
        except http.FetchError as e:
            raise TTSError(f"azure: {e}") from e
        if len(audio) < 500:
            raise TTSError("azure: empty audio")
        with open(out_path, "wb") as f:
            f.write(audio)
        return out_path
