"""Optional audio check: transcribe each rendered segment and compare with the text.

Catches TTS engines that skip, repeat or invent words. Uses faster-whisper
(open source, runs locally; `pip install faster-whisper`). Character error rate
(CER) is computed on normalised text: lowercase, no punctuation, digits spelled.
ASR itself makes mistakes on names, so the threshold is deliberately loose and a
flagged segment means "listen to this one", not "this one is wrong".
"""
import re
import subprocess

from .edition import EDITIONS
from .review import load_approved
from .speech import load_lexicon, speech_text
from .util import ROOT, load_json, write_json

DEFAULT_THRESHOLD = 0.20
MIN_CHARS = 40  # ASR is unreliable on one-word headings ("Волинь."); those are recorded, not judged


def normalise(text):
    t = speech_text(text, load_lexicon(), spell_digits=True, lowercase=True)
    t = t.replace("’", "'").replace("ʼ", "'")
    t = re.sub(r"[^\w' ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def cer(ref, hyp):
    """Levenshtein distance / len(ref), on characters."""
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i]
        for j, hc in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / len(ref)


def _load_audio(path):
    import numpy as np

    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", "16000", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def verify(date, model_size="small", threshold=DEFAULT_THRESHOLD, model_dir=None):
    from faster_whisper import WhisperModel

    approved = load_approved(date)
    render = load_json(EDITIONS / date / "render.json")
    model = WhisperModel(model_size, device="cpu", compute_type="int8", download_root=model_dir)
    texts = {seg["id"]: " ".join(s["text"] for s in seg["sentences"]) for seg in approved["segments"]}
    results, failed = [], []
    for seg in render["segments"]:
        parts, _ = model.transcribe(_load_audio(ROOT / seg["file"]), language="uk", beam_size=5)
        hyp = normalise(" ".join(p.text for p in parts))
        ref = normalise(texts[seg["id"]])
        score = round(cer(ref, hyp), 3)
        results.append({"id": seg["id"], "cer": score, "transcript": hyp})
        if score > threshold and len(ref) >= MIN_CHARS:
            failed.append(seg["id"])
    render["asr"] = {"model": f"faster-whisper-{model_size}", "threshold": threshold,
                     "mean_cer": round(sum(r["cer"] for r in results) / max(1, len(results)), 3),
                     "failed": failed, "segments": results}
    write_json(EDITIONS / date / "render.json", render)
    return render["asr"]
