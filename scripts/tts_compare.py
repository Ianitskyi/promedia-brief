#!/usr/bin/env python3
"""Render the same Ukrainian test script with several TTS providers and compare them.

    python scripts/tts_compare.py --providers piper google azure --out /tmp/tts-compare

For each provider: render time, characters, estimated cost, and (with faster-whisper
installed) character error rate of an ASR round-trip — an objective proxy for reading
accuracy. Naturalness, stress and name pronunciation still need human listening:
the script writes one audio file per provider for a blind listening test.
Paid providers obey the same BRIEF_ALLOW_PAID_TTS / BRIEF_MAX_TTS_USD guard as production.
"""
import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from brief import audio, tts  # noqa: E402
from brief.speech import load_lexicon, speech_text  # noqa: E402
from brief.verify import cer, normalise  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", nargs="+", default=["piper"])
    ap.add_argument("--script", default=str(ROOT / "docs" / "tts" / "test-script.txt"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--asr-model-dir")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    lines = [x.strip() for x in pathlib.Path(a.script).read_text(encoding="utf-8").splitlines() if x.strip()]
    lexicon = load_lexicon()
    asr = None
    try:
        from faster_whisper import WhisperModel

        asr = WhisperModel("small", device="cpu", compute_type="int8", download_root=a.asr_model_dir)
    except ImportError:
        print("faster-whisper not installed: skipping ASR check", file=sys.stderr)

    results = []
    for name in a.providers:
        p = tts.get(name)
        texts = [speech_text(x, lexicon, p.spell_digits, p.lowercase, p.transliterate_latin) for x in lines]
        chars = sum(len(t) for t in texts)
        row = {"provider": name, "voice": p.voice, "characters": chars, "estimated_cost_usd": round(p.estimate_cost(chars), 4)}
        try:
            tts.guard_cost(p, chars)
            work = out / name
            work.mkdir(exist_ok=True)
            t0 = time.time()
            parts = []
            for i, t in enumerate(texts):
                f = work / f"{i:02d}.{p.output_ext}"
                p.synthesize(t, f)
                parts += [("file", f), ("pause", 350)]
            row["render_sec"] = round(time.time() - t0, 1)
            final = out / f"{name}.mp3"
            row["duration_sec"] = round(audio.assemble(parts, final, work / "asm"), 1)
            row["file"] = str(final)
            if asr:
                from brief.verify import _load_audio

                segs, _ = asr.transcribe(_load_audio(final), language="uk", beam_size=5)
                hyp = normalise(" ".join(s.text for s in segs))
                row["asr_cer"] = round(cer(normalise(" ".join(lines)), hyp), 3)
                row["asr_transcript"] = hyp
        except Exception as e:  # missing key, refused paid run, API error: record and continue
            row["error"] = str(e)[:300]
        results.append(row)
        print(json.dumps({k: v for k, v in row.items() if k != "asr_transcript"}, ensure_ascii=False))
    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
