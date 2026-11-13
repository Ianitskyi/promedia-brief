"""Put the day's voiced spoken edition into the one player on the home page.

The home page and demo.html play the single item in demo/index.json. The daily edition
replaces yesterday's there (docs/ONE_PLAYER_ROADMAP.md, stage 2); yesterday's daily audio is
deleted. Hand-made demos (22 and 29 October) stay in demo/ as archive files.
"""
import shutil

from .edition import EDITIONS
from .review import load_script
from .util import ROOT, load_json, write_json

DEMO = ROOT / "demo"
SUFFIX = "daily"


class FeatureError(RuntimeError):
    pass


def feature(date, variant=SUFFIX, require_asr=True):
    spoken = load_script(date, "spoken")
    render = load_json(EDITIONS / date / f"render-{variant}.json")
    if render is None:
        raise FeatureError(f"no render-{variant}.json for {date}")
    if render.get("script_sha256") != spoken["script_sha256"]:
        raise FeatureError("the audio was rendered from a different text")
    if render.get("provider") == "mock":
        raise FeatureError("mock audio is never published")
    asr = render.get("asr")
    if require_asr and (not asr or asr.get("failed")):
        raise FeatureError("the audio check (verify-audio) did not pass: "
                           + (", ".join(asr["failed"]) if asr else "not run"))
    name = f"{date}-{SUFFIX}"
    DEMO.mkdir(exist_ok=True)
    shutil.copyfile(ROOT / render["full"]["file"], DEMO / f"{name}.mp3")
    # Each segment's audio too: the site plays them in the listener's order (topics, region).
    parts = DEMO / name
    shutil.rmtree(parts, ignore_errors=True)
    parts.mkdir()
    audio = {}
    for r in render["segments"]:
        shutil.copyfile(ROOT / r["file"], parts / f"{r['id']}.mp3")
        audio[r["id"]] = {"audio": f"demo/{name}/{r['id']}.mp3", "duration_sec": r["duration_sec"]}
    if set(audio) != {seg["id"] for seg in spoken["segments"] if seg["sentences"]}:
        raise FeatureError("the audio segments do not match the text")
    approved = {seg["id"]: seg for seg in load_script(date, "approved")["segments"]}

    def about(seg):
        """Topics and regions of the approved stories a spoken story was made from."""
        src = [approved[i] for i in seg.get("from_stories", []) if i in approved]
        topics = list(dict.fromkeys(t for a in src for t in a.get("topics", [])))
        regions = list(dict.fromkeys(r for a in src for r in a.get("regions", [])))
        return {"topics": topics, "regions": regions}

    write_json(DEMO / f"{name}.json", {
        "date": date,
        "variant": SUFFIX,
        "audio": f"demo/{name}.mp3",
        "provider": render.get("provider"),
        "model": render.get("model"),
        "voice": render.get("voice"),
        "service_voice": render.get("service_voice"),
        "duration_sec": render["duration_sec"],
        "asr_mean_cer": asr.get("mean_cer") if asr else None,
        "approved_by": "Автоматичний випуск: кожне число й назва звірені з першоджерелами",
        "description": (f"Щоденний випуск BRIEF. Новин у випуску: {spoken['stories']}. Кожне число, назва й "
                        "цитата звірені з публікаціями. Посилання на першоджерела — під кожною новиною."),
        "script_sha256": spoken["script_sha256"],
        "sonic": {"intro": "audio/intro.mp3", "outro": "audio/outro.mp3"},
        "segments": [{"id": seg["id"], "kind": seg["kind"], "block": seg["block"], "title": seg.get("title"),
                      **audio[seg["id"]], **(about(seg) if seg["kind"] == "story" else {}),
                      "text": [s["text"] for s in seg["sentences"]],
                      "sources": [{"name": x["name"], "url": x["url"]} for x in seg.get("sources", [])]}
                     for seg in spoken["segments"] if seg["sentences"]],
    })
    for old in DEMO.glob(f"*-{SUFFIX}*"):  # yesterday's daily edition: mp3, json and segments
        if old.name.split(".")[0] != name:
            shutil.rmtree(old) if old.is_dir() else old.unlink()
    write_json(DEMO / "index.json", {"demos": [{"id": name, "date": date, "variant": SUFFIX,
                                                "file": f"demo/{name}.json"}]})
    return DEMO / f"{name}.mp3"
