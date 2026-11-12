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
    retold = spoken["retold"]
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
        "description": (f"Щоденний випуск BRIEF. {retold} з {spoken['stories']} сюжетів переказано для "
                        "усного мовлення; кожне число, назва й цитата звірені з публікаціями. "
                        "Посилання на першоджерела — під кожним сюжетом."),
        "script_sha256": spoken["script_sha256"],
        "segments": [{"kind": seg["kind"], "block": seg["block"], "title": seg.get("title"),
                      "text": [s["text"] for s in seg["sentences"]],
                      "sources": [{"name": x["name"], "url": x["url"]} for x in seg.get("sources", [])]}
                     for seg in spoken["segments"] if seg["sentences"]],
    })
    for old in DEMO.glob(f"*-{SUFFIX}.*"):  # yesterday's daily edition
        if not old.name.startswith(name + "."):
            old.unlink()
    write_json(DEMO / "index.json", {"demos": [{"id": name, "date": date, "variant": SUFFIX,
                                                "file": f"demo/{name}.json"}]})
    return DEMO / f"{name}.mp3"
