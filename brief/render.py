"""Stage 8: synthesize the *approved* script and assemble audio.

* Only editions/<date>/approved.json is read; its sha256 is re-verified first.
* Each sentence is synthesized separately (exact text, natural pauses, precise
  control); long sentences are chunked without loss (asserted).
* Synthesized chunks are cached by content hash, so a re-run after a failure
  resumes where it stopped and never pays twice for the same text.
"""
import hashlib
import os
import pathlib
import shutil
import tempfile
import time

from . import audio, tts
from .edition import EDITIONS
from .review import load_approved
from .speech import load_lexicon, load_stress, speech_text
from .util import ROOT, config, iso, now_utc, write_json

PAUSE_SENTENCE_MS = 350
PAUSE_STORY_MS = 1300  # a clear gap between stories
PAUSE_CHUNK_MS = 120
SONIC = {"intro": ROOT / "audio" / "intro.mp3", "bumper": ROOT / "audio" / "bumper.mp3",
         "outro": ROOT / "audio" / "outro.mp3"}


def tts_text(sentence_text, provider, lexicon):
    text = speech_text(sentence_text, lexicon, spell_digits=provider.spell_digits, lowercase=provider.lowercase,
                       transliterate=provider.transliterate_latin,
                       stress=load_stress() if provider.stress_marks or provider.auto_stress else None)
    if provider.auto_stress:
        from .speech import auto_stress

        text = auto_stress(text)
    return text


def mood(seg, moods):
    """Tone of a story for engines that take tone tags: the first mood whose markers occur in it."""
    if seg["kind"] != "story":
        return None
    text = " ".join(s["text"] for s in seg["sentences"]).lower()
    for name, m in moods.items():
        if isinstance(m, dict) and any(k in text for k in m.get("markers", [])):
            return name
    return None


def plan(approved, provider, lexicon, moods=None):
    """What will be sent to TTS, segment by segment. Pure function (used by tests and cost estimates)."""
    measure = (lambda s: len(s.encode("utf-8"))) if provider.measure_bytes else len
    moods = moods if moods is not None else config("editorial.json").get("tts_moods", {})
    out = []
    for seg in approved["segments"]:
        if not seg["sentences"]:
            continue
        tone = mood(seg, moods) if provider.audio_tags else None
        tag = moods.get(tone, {}).get("tag") if tone else (moods.get("neutral", {}).get("tag") if provider.audio_tags
                                                           and seg["kind"] == "story" else None)
        sents = []
        for i, s in enumerate(seg["sentences"]):
            text = tts_text(s["text"], provider, lexicon)
            chunks = tts.chunk_text(text, provider.max_chars, measure)
            if tag and i == 0:
                chunks = [f"{tag} {chunks[0]}"] + chunks[1:]  # the tag sets the tone; it is not spoken
            sents.append({"id": s["id"], "text": text, "chunks": chunks, "mood": tone})
        out.append({"id": seg["id"], "kind": seg["kind"], "block": seg["block"], "sentences": sents})
    return out


def _cache_key(provider, text):
    return hashlib.sha256(f"{provider.name}|{provider.voice}|{text}".encode("utf-8")).hexdigest()[:24]


def render(date, provider_name="mock", voice=None, out_dir=None, cache_dir=None, variant=None, service_voice=None):
    """variant: render an alternative voicing (e.g. a paid demo) next to the published one:
    audio goes to editions/<date>/variants/<variant>/, the manifest to render-<variant>.json."""
    started = time.time()
    approved = load_approved(date)
    provider = tts.get(provider_name, voice=voice)
    lexicon = load_lexicon()
    segments = plan(approved, provider, lexicon)
    characters = sum(len(c) for seg in segments for s in seg["sentences"] for c in s["chunks"])
    cost = tts.guard_cost(provider, characters)
    # Service lines (intro, reminder, outro) in a second voice so they stand apart from the news.
    ed = config("editorial.json")["edition"]
    if service_voice is None:
        service_voice = ed.get("tts_service_voice") if provider_name == ed.get("tts_provider") else None
    service = tts.get(provider_name, voice=service_voice) if service_voice else provider
    service_kinds = set(ed.get("tts_service_kinds", [])) if service_voice else set()
    # Post-processing of the synthesized voice (free: no new TTS calls, works on cached audio).
    # BRIEF_TEMPO speeds every voice up; BRIEF_SERVICE_TEMPO / BRIEF_SERVICE_PITCH (semitones,
    # negative = lower) adjust the service voice on top.
    # BRIEF_ALTERNATE_VOICES=1: the two voices take turns reading stories, like two hosts.
    alternate = service_voice and os.environ.get("BRIEF_ALTERNATE_VOICES") == "1"
    # Per-voice pace controls. BRIEF_TEMPO remains a global multiplier for backward compatibility.\n    # A/B test values are passed as environment variables (do not change production defaults).\n    news_tempo = float(os.environ.get("BRIEF_TEMPO", "1.0")) * float(os.environ.get("BRIEF_NEWS_TEMPO", "1.0"))
    if not 0.80 <= news_tempo <= 1.20:\n        raise ValueError("news tempo must be between 0.80 and 1.20")\n    news_af = audio.voice_filter(news_tempo)
    service_tempo = news_tempo * float(os.environ.get("BRIEF_SERVICE_TEMPO", "1.0"))\n    if not 0.80 <= service_tempo <= 1.20:\n        raise ValueError("service tempo must be between 0.80 and 1.20")\n    service_af = audio.voice_filter(service_tempo, float(os.environ.get("BRIEF_SERVICE_PITCH", "0")))

    default_dir = EDITIONS / date / ("variants/" + variant if variant else "audio")
    out_dir = pathlib.Path(out_dir or default_dir)
    cache_dir = pathlib.Path(cache_dir or EDITIONS / date / ".tts-cache")
    out_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)
    work = pathlib.Path(tempfile.mkdtemp(prefix="brief-render-"))
    calls, cached = 0, 0
    rendered = []
    try:
        story_no = 0
        for seg in segments:
            parts = []
            voice_of = service if seg["kind"] in service_kinds else provider
            if alternate and seg["kind"] == "story":
                voice_of = service if story_no % 2 else provider
                story_no += 1
            for si, s in enumerate(seg["sentences"]):
                for ci, chunk in enumerate(s["chunks"]):
                    path = cache_dir / f"{_cache_key(voice_of, chunk)}.{voice_of.output_ext}"
                    if path.exists() and path.stat().st_size > 0:
                        cached += 1
                    else:
                        tmp = path.with_suffix(".part." + voice_of.output_ext)
                        voice_of.synthesize(chunk, tmp)
                        tmp.replace(path)  # only complete files enter the cache
                        calls += 1
                    parts.append(("file", path, service_af if voice_of is service and service is not provider else news_af))
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

        # Default full edition: intro sting, national, reminder, bumper, regional roundup, outro.
        by_id = {r["id"]: r for r in rendered}
        order = [("file", SONIC["intro"])]
        for seg in approved["segments"]:
            if seg["block"] in ("intro", "national", "reminder") and seg["id"] in by_id:
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
        "service_voice": service.voice if service is not provider else None,
        "voice_filters": {"news": news_af, "service": service_af},
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
    if variant:
        manifest["variant"] = variant
    write_json(EDITIONS / date / (f"render-{variant}.json" if variant else "render.json"), manifest)
    return manifest
