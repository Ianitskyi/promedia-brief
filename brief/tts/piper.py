"""Piper (open source, runs locally, no per-character cost).

Voice: uk_UA-ukrainian_tts-medium (dataset CC0) from rhasspy/piper-voices.
The model reads lowercase Cyrillic only and does not expand digits, so the speech
layer lowercases and spells numbers for it. Quality is below commercial cloud
voices; useful as a free fallback and for dry runs. Piper itself is GPL-3.0
(we only run it as a separate tool, we do not distribute it).
"""
import os
import subprocess
import sys

from . import register
from .base import Provider, TTSError

SPEAKERS = {"lada": 0, "mykyta": 1, "tetiana": 2}


@register
class PiperProvider(Provider):
    name = "piper"
    paid = False
    max_chars = 1200
    output_ext = "wav"
    default_voice = "tetiana"
    spell_digits = True
    lowercase = True
    transliterate_latin = True  # the model has no Latin phonemes and silently drops such words

    def synthesize(self, text, out_path):
        model = os.environ.get("BRIEF_PIPER_MODEL")
        if not model or not os.path.exists(model):
            raise TTSError("piper: set BRIEF_PIPER_MODEL to the .onnx voice file")
        speaker = SPEAKERS.get(self.voice, 0)
        length_scale = self.options.get("length_scale", os.environ.get("BRIEF_PIPER_LENGTH_SCALE", "1.0"))
        r = subprocess.run(
            [sys.executable, "-m", "piper", "-m", model, "-s", str(speaker), "--length-scale", str(length_scale),
             "-f", str(out_path)],
            input=text.encode("utf-8"), capture_output=True,
        )
        if r.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
            raise TTSError(f"piper failed: {r.stderr.decode('utf-8', 'replace')[-300:]}")
        return out_path
