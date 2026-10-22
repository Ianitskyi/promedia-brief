"""StyleTTS2 Ukrainian (open source, runs locally on CPU, no per-character cost).

Model: patriotyk/styletts2_ukrainian_multispeaker_hifigan (MIT), voice styles from the
patriotyk/styletts2-ukrainian space. Files are fetched from Hugging Face at pinned
revisions and cached (HF_HOME). Stress marks come from ukrainian-word-stress, phonemes
from ipa-uk. Chosen by the owner on 2026-10-21 after a listening test ("диктор 2").

The model reads one sentence at a time at speed 1.3; the result is then sped up with
ffmpeg atempo (pitch preserved) to ≈155 words per minute, a typical news-reading pace.
Dependencies: requirements-styletts2.txt (torch CPU, ~1 GB with models).
"""
import os
import re
import subprocess
import tempfile
from unicodedata import normalize

from . import register
from .base import Provider, TTSError

MODEL_REPO = "patriotyk/styletts2_ukrainian_multispeaker_hifigan"
MODEL_REVISION = "dcca8ce02382d91d95123c93f8b01bc90fe17cfc"
STYLE_REPO = "patriotyk/styletts2-ukrainian"
STYLE_REVISION = "b02909e4c9f001865bf71633d76fee7110f657a3"
# voice id -> style file in STYLE_REPO
VOICES = {"male_2": "voices/Михайло Тишин.pt", "male_4": "voices/Юрій Вихованець.pt",
          "female_3": "voices/Олена Шверк.pt"}
SAMPLE_RATE = 24000

_engine = None


def _load():
    global _engine
    if _engine is None:
        try:
            import torch
            from huggingface_hub import hf_hub_download
            from ipa_uk import ipa
            from styletts2_inference.models import StyleTTS2
            from ukrainian_word_stress import Stressifier
        except ImportError as e:
            raise TTSError(f"styletts2: install requirements-styletts2.txt ({e})")
        torch.manual_seed(0)  # the model draws its diffusion noise once, at load time
        model = StyleTTS2(config_path=hf_hub_download(MODEL_REPO, "config.yml", revision=MODEL_REVISION),
                          weights_path=hf_hub_download(MODEL_REPO, "pytorch_model.bin", revision=MODEL_REVISION))
        model.eval()
        _engine = {"torch": torch, "model": model, "stress": Stressifier(), "ipa": ipa, "styles": {},
                   "download": hf_hub_download}
    return _engine


def _style(engine, voice):
    if voice not in VOICES:
        raise TTSError(f"styletts2: unknown voice {voice!r}; available: {', '.join(VOICES)}")
    if voice not in engine["styles"]:
        path = engine["download"](STYLE_REPO, VOICES[voice], repo_type="space", revision=STYLE_REVISION)
        engine["styles"][voice] = engine["torch"].load(path)
    return engine["styles"][voice]


def prepare(text):
    """Punctuation the model expects (same rules as the model author's demo)."""
    t = normalize("NFKC", text.strip()).replace('"', "")
    t = re.sub(r"[‐‑‒–—―−]", "-", t)
    t = re.sub(r" - ", ": ", t)
    if t and t[-1] not in ".?!:-":
        t += "."
    return t


def parts(text):
    """Split at sentence punctuation; the model is trained on single sentences."""
    return [p for p in re.split(r"(?<=[.?!:])\s+", text) if p.strip()]


@register
class StyleTTS2Provider(Provider):
    name = "styletts2"
    paid = False
    max_chars = 500
    output_ext = "wav"
    default_voice = "male_2"
    spell_digits = True
    transliterate_latin = True  # the phonemizer has no Latin letters
    stress_marks = True  # ukrainian-word-stress keeps marks that are already there

    def synthesize(self, text, out_path):
        engine = _load()
        style = _style(engine, self.voice)
        speed = float(self.options.get("speed", os.environ.get("BRIEF_STYLETTS2_SPEED", "1.3")))
        tempo = float(self.options.get("tempo", os.environ.get("BRIEF_STYLETTS2_TEMPO", "1.18")))
        torch = engine["torch"]
        wavs = []
        with torch.no_grad():
            for p in parts(prepare(text)):
                tokens = engine["model"].tokenizer.encode(engine["ipa"](engine["stress"](p)))
                if len(tokens):
                    wavs.append(engine["model"](tokens, speed=speed, s_prev=style).cpu())
        if not wavs:
            raise TTSError(f"styletts2: nothing to say for {text!r}")
        import soundfile

        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "raw.wav")
            soundfile.write(raw, torch.cat(wavs).numpy(), SAMPLE_RATE)
            r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-af", f"atempo={tempo}", str(out_path)],
                               capture_output=True)
        if r.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) < 1000:
            raise TTSError(f"styletts2 tempo step failed: {r.stderr.decode('utf-8', 'replace')[-300:]}")
        return out_path
