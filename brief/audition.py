"""Render a private, unapproved spoken-language audition from the archived demo.

This is strictly a voice audition: it does not read/write approved.json,
does not update demo/index.json and cannot publish to the BRIEF website.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import tempfile

from . import audio, tts
from .util import ROOT

SCRIPT = ROOT / "docs" / "tts" / "spoken-demo-2026-10-22.md"
MALE_ID = "TEyBWD5tAHAWqAGEv6yI"
FEMALE_ID = "0ZQZuw8Sn4cU0rN1Tm2K"


def parse_script(md):
    intro = re.search(r"(?m)^Вступ:\s*(.+)$", md)
    outro = re.search(r"(?m)^Завершення:\s*(.+)$", md)
    if not intro or not outro:
        raise ValueError("Script is missing intro or closing")
    stories = re.findall(r"(?m)^\*\*Для озвучення:\*\*\s*(.+)$", md)
    if not stories:
        raise ValueError("No story paragraphs in spoken draft")
    if len(stories) != 12:
        raise ValueError(f"Expected 12 archived stories, found {len(stories)}")
    return [
        ("Yaroslava", intro.group(1).strip()),
        ("Yevhen", "Новини України."),
        *[( "Yevhen", text.strip()) for text in stories[:7]],
        ("Yaroslava", "А тепер — новини регіонів."),
        *[( "Yevhen", text.strip()) for text in stories[7:]],
        ("Yaroslava", outro.group(1).strip()),
    ]


def audition(output, *, script=SCRIPT):
    """Explicit paid consent; private audio artifact only, no automatic publication."""
    if os.environ.get("BRIEF_ALLOW_PAID_TTS") != "1":
        raise RuntimeError("Paid speech audition requires BRIEF_ALLOW_PAID_TTS=1")
    parts = parse_script(pathlib.Path(script).read_text(encoding="utf-8"))
    male = tts.get("elevenlabs", voice=MALE_ID)
    female = tts.get("elevenlabs", voice=FEMALE_ID)
    chars = sum(len(text) for _, text in parts)
    cost = tts.guard_cost(male, chars)
    output = pathlib.Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    male_speed = float(os.environ.get("BRIEF_YEVHEN_TEMPO", "1.0"))
    female_speed = float(os.environ.get("BRIEF_YAROSLAVA_TEMPO", "1.0"))
    if not 0.8 <= male_speed <= 1.2 or not 0.8 <= female_speed <= 1.2:
        raise ValueError("Voice tempo must be between 0.8 and 1.2")
    male_filter = audio.voice_filter(male_speed)
    female_filter = audio.voice_filter(female_speed)
    with tempfile.TemporaryDirectory(prefix="brief-audition-") as tmp:
        tmp = pathlib.Path(tmp)
        timeline = []
        with open(tmp / "script.txt", "w", encoding="utf-8") as f:
            for index, (name, text) in enumerate(parts):
                f.write(f"{name}: {text}\n")
                provider = male if name == "Yevhen" else female
                mp3 = tmp / f"part-{index:02d}.mp3"
                provider.synthesize(text, mp3)
                timeline.append(("file", mp3, male_filter if name == "Yevhen" else female_filter))
                timeline.append(("pause", 900 if name == "Yevhen" else 550))
        audio.assemble(timeline, output, tmp / "work")
    info = {
        "type": "UNAPPROVED_PRIVATE_AUDITION",
        "published": False,
        "script": str(script),
        "script_sha256": hashlib.sha256(pathlib.Path(script).read_bytes()).hexdigest(),
        "male": {"name": "Yevhen", "voice_id": MALE_ID, "tempo": male_speed},
        "female": {"name": "Yaroslava", "voice_id": FEMALE_ID, "tempo": female_speed},
        "stories": 12,
        "characters": chars,
        "estimated_cost_usd": round(cost, 4),
        "audio": output.name,
    }
    output.with_suffix(".json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n",
                                           encoding="utf-8")
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="audition/brief-2026-10-22-spoken.mp3")
    args = parser.parse_args()
    print(json.dumps(audition(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
