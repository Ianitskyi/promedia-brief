"""Stage 8: synthesize the *approved* script and assemble audio.

* Only editions/<date>/approved.json is read; its sha256 is re-verified first.
* Each sentence is synthesized separately (exact text, natural pauses, precise
  control); long sentences are chunked without loss (asserted).
* Synthesized chunks are cached by content hash, so a re-run after a failure
  resumes where it stopped and never pays twice for the same text.
"""
import hashlib
import pathlib
import shutil
import tempfile
import time

from . import audio, tts
from .edition import EDITIONS
from .review import load_approved
from .speech import load_lexicon, speech_text
from .util import ROOT, iso, now_utc, write_json

PAUSE_SENTENCE_MS = 350
PAUSE_STORY_MS = 700
PAUSE_CHUNK_MS = 120
SONIC = {"intro": ROOT / "audio" / "intro.mp3", "bumper": ROOT / "audio" / "bumper.mp3",
         "outro": ROOT / "audio" / "outro.mp3"}


def tts_text(sentence_text, provider, lexicon):
    return speech_text(sentence_text, lexicon, spell_digits=provider.spell_digits, lowercase=provider.lowercase,
                       transliterate=provider.transliterate_latin)


def plan(approved, provider, lexicon):
    """What will be sent to TTS, segment by segment. Pure function (used by tests and cost estimates)."""
    measure = (lambda s: len(s.encode("utf-8"))) if provider.measure_bytes else len
    out = []
    for seg in approved["segments"]:
        if not seg["sentences"]:
            continue
        sents = []
        for s in seg["sentences"]:
            text = tts_text(s["text"], provider, lexicon)
            sents.append({"id": s["id"], "text": text, "chunks": tts.chunk_text(text, provider.max_chars, measure)})
        out.append({"id": seg["id"], "kind": seg["kind"], "block": seg["block"], "sentences": sents})
    return out


def _cache_key(provider, text):
    return hashlib.sha256(f"{provider.name}|{provider.voice}|{text}".encode("utf-8")).hexdigest()[:24]


def render(date, provider_name="mock", voice=None, out_dir=None, cache_dir=None):
    started = time.time()
    approved = load_approved(date)
    provider = tts.get(provider_name, voice=voice)
    lexicon = load_lexicon()
    segments = plan(approved, provider, lexicon)
    characters = sum(len(c) for seg in segments for s in seg["sentences"] for c in s["chunks"])
    cost = tts.guard_cost(provider, characters)

    out_dir = pathlib.Path(out_dir or EDITIONS / date / "audio")
    cache_dir = pathlib.Path(cache_dir or EDITIONS / date / ".tts-cache")
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    work = pathlib.Path(tempfile.mkdtemp(prefix="brief-render-"))
    calls, cached = 0, 0
    rendered = []
    try:
        for seg in segments:
            parts = []
            for si, s in enumerate(seg["sentences"]):
                for ci, chunk in enumerate(s["chunks"]):
                    path = cache_dir / f"{_cache_key(provider, chunk)}.{provider.output_ext}"
                    if path.exists() and path.stat().st_size > 0:
                        cached += 1
                    else:
                        tmp = path.with_suffix(".part." + provider.output_ext)
                        provider.synthesize(chunk, tmp)
                        tmp.replace(path)  # only complete files enter the cache
                        calls += 1
                    parts.append(("file", path))
                    if ci < len(s["chunks"]) - 1:
                        parts.append(("pause", PAUSE_CHUNK_MS))
                if si < len(seg["sentences"]) - 1:
                    parts.append(("pause", PAUSE_SENTENCE_MS))
            parts.append(("pause", PAUSE_STORY_MS if seg["kind"] == "story" else PAUSE_SENTENCE_MS))
            dst = out_dir / f"{seg['id']}.mp3"
            dur = audio.assemble(parts, dst, work / seg["id"])
            rendered.append({
                "id": seg["id"], "kind": seg["kind"], "block": seg["block"],
                "file": dst.relative_to(ROOT).as_posix() if dst.is_relative_to(ROOT) else str(dst),
                "duration_sec": round(dur, 2),
                "sentences": [{"id": s["id"], "text_sha256": hashlib.sha256(s["text"].encode()).hexdigest(),
                               "chunks": len(s["chunks"])} for s in seg["sentences"]],
            })

        # Default full edition: intro sting, national, bumper, regional roundup, outro.
        by_id = {r["id"]: r for r in rendered}
        order = [("file", SONIC["intro"])]
        for seg in approved["segments"]:
            if seg["block"] in ("intro", "national") and seg["id"] in by_id:
                order.append(("file", ROOT / by_id[seg["id"]]["file"]))
            if seg["kind"] == "transition":
                order.append(("file", SONIC["bumper"]))
        for seg in approved["segments"]:
            if seg["block"] in ("regional", "outro") and seg["id"] in by_id:
                order.append(("file", ROOT / by_id[seg["id"]]["file"]))
        order.append(("file", SONIC["outro"]))
        full = out_dir / f"brief-{date}.mp3"
        full_dur = audio.assemble(order, full, work / "full")
    finally:
        shutil.rmtree(work, ignore_errors=True)

    manifest = {
        "date": date,
        "script_sha256": approved["script_sha256"],
        **provider.describe(),
        "rendered_at": iso(now_utc()),
        "elapsed_sec": round(time.time() - started, 1),
        "characters": characters,
        "estimated_cost_usd": round(cost, 4),
        "api_calls": calls,
        "cached_chunks": cached,
        "segments": rendered,
        "full": {"file": full.relative_to(ROOT).as_posix() if full.is_relative_to(ROOT) else str(full),
                 "duration_sec": round(full_dur, 2)},
        "duration_sec": round(full_dur, 2),
    }
    write_json(EDITIONS / date / "render.json", manifest)
    return manifest
