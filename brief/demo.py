"""Keep a rendered variant (e.g. a paid-voice edition shown to partners) as a permanent demo.

Editions are deleted after 7 days; demo/ is not. A demo holds the full mp3, the script
that was voiced and the sources of every story, so it can be checked later like any edition.
"""
import shutil

from .edition import EDITIONS
from .review import load_approved
from .util import ROOT, load_json, write_json

DEMO = ROOT / "demo"


def save(date, variant):
    approved = load_approved(date)
    render = load_json(EDITIONS / date / f"render-{variant}.json")
    if render is None:
        raise FileNotFoundError(f"no render-{variant}.json for {date}")
    if render.get("script_sha256") != approved["script_sha256"]:
        raise RuntimeError("the rendered audio is for a different script")
    asr = render.get("asr")
    if not asr or asr.get("failed"):
        raise RuntimeError("demo needs a passed ASR check (brief verify-audio --variant ...)")
    name = f"{date}-{variant}"
    DEMO.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / render["full"]["file"], DEMO / f"{name}.mp3")
    write_json(DEMO / f"{name}.json", {
        "date": date,
        "variant": variant,
        "audio": f"demo/{name}.mp3",
        "provider": render.get("provider"),
        "model": render.get("model"),
        "voice": render.get("voice"),
        "service_voice": render.get("service_voice"),
        "duration_sec": render["duration_sec"],
        "asr_mean_cer": asr.get("mean_cer"),
        "approved_by": approved["approved_by"],
        "script_sha256": approved["script_sha256"],
        "segments": [{"kind": seg["kind"], "block": seg["block"], "title": seg.get("title"),
                      "text": [s["text"] for s in seg["sentences"]],
                      "sources": [{"name": x["name"], "url": x["url"]} for x in seg.get("sources", [])]}
                     for seg in approved["segments"] if seg["sentences"]],
    })
    index = load_json(DEMO / "index.json", {"demos": []})
    index["demos"] = [d for d in index["demos"] if d["id"] != name] + [
        {"id": name, "date": date, "variant": variant, "file": f"demo/{name}.json"}]
    index["demos"].sort(key=lambda d: d["id"], reverse=True)
    write_json(DEMO / "index.json", index)
    return DEMO / f"{name}.mp3"
