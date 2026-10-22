"""A/B sample for one TTS engine: the same sentences without and with dictionary stress marks.

    python scripts/tts_ab.py --provider elevenlabs --out ab
writes ab/a-no-stress.mp3 and ab/b-stress.mp3 (numbers are spelled out in both).
Short on purpose: it spends a few hundred characters of a paid API (cost guard applies).
"""
import argparse
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from brief import audio, tts  # noqa: E402
from brief.render import tts_text  # noqa: E402
from brief.speech import load_lexicon  # noqa: E402

SAMPLE = [
    "Унаслідок нічної атаки на Київ 22 жовтня загинула людина, ще 24 постраждали, серед них двоє 15-річних підлітків.",
    "Спецпосланець Дональда Трампа Стів Віткофф заявив, що очільник Кремля готовий до тристоронніх переговорів.",
    "На Хмельниччині від початку 2026 року сталося 177 пожеж, у яких загинули 11 людей.",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="elevenlabs")
    ap.add_argument("--voice")
    ap.add_argument("--out", default="ab")
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    lexicon = load_lexicon()
    for name, stress in (("a-no-stress", "0"), ("b-stress", "1")):
        os.environ["BRIEF_ELEVENLABS_STRESS"] = stress
        p = tts.get(a.provider, voice=a.voice)
        texts = [tts_text(s, p, lexicon) for s in SAMPLE]
        tts.guard_cost(p, sum(len(t) for t in texts))
        parts = []
        for i, t in enumerate(texts):
            f = out / f"{name}-{i}.{p.output_ext}"
            p.synthesize(t, f)
            parts += [("file", f), ("pause", 600)]
            print(name, t)
        audio.assemble(parts, out / f"{name}.mp3", out / f"work-{name}")


if __name__ == "__main__":
    main()
