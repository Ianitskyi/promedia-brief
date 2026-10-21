"""Stage 9: publish an approved, fully rendered edition (fail closed).

Nothing is written unless every check passes, so an incomplete or unapproved
edition can never become `editions/latest.json` silently.
"""
import shutil

from .edition import EDITIONS
from .review import load_approved
from .util import ROOT, config, iso, load_json, now_utc, write_json


class PublishError(RuntimeError):
    pass


def validate(date, allow_mock=False):
    approved = load_approved(date)
    render = load_json(EDITIONS / date / "render.json")
    problems = []
    if render is None:
        raise PublishError(f"{date}: not rendered")
    if render["script_sha256"] != approved["script_sha256"]:
        problems.append("audio was rendered from a different script than the approved one")
    if render["provider"] == "mock" and not allow_mock:
        problems.append("audio is a mock placeholder (provider=mock)")
    rendered = {r["id"]: r for r in render["segments"]}
    for seg in approved["segments"]:
        if not seg["sentences"]:
            continue
        r = rendered.get(seg["id"])
        if r is None:
            problems.append(f"segment {seg['id']} has no audio")
            continue
        if not (ROOT / r["file"]).exists() or r["duration_sec"] <= 0:
            problems.append(f"segment {seg['id']}: audio file missing or empty")
        if [s["id"] for s in seg["sentences"]] != [s["id"] for s in r["sentences"]]:
            problems.append(f"segment {seg['id']}: rendered sentences differ from approved ones")
    asr = render.get("asr")
    if asr and asr.get("failed"):
        problems.append("ASR check flagged segments: " + ", ".join(asr["failed"]))
    if not (ROOT / render["full"]["file"]).exists():
        problems.append("full edition file missing")
    if problems:
        raise PublishError(f"{date}: refusing to publish:\n- " + "\n- ".join(problems))
    return approved, render


def public_edition(approved, render):
    regions = {r["id"]: r["name"] for r in config("regions.json")["regions"]}
    audio = {r["id"]: r for r in render["segments"]}
    segs = []
    for seg in approved["segments"]:
        a = audio.get(seg["id"])
        segs.append({
            "id": seg["id"], "kind": seg["kind"], "block": seg["block"], "region": seg.get("region"),
            "title": seg.get("title"), "topics": seg.get("topics", []), "must_include": seg.get("must_include", False),
            "text": [s["text"] for s in seg["sentences"]],
            "sources": [{"name": s["name"], "url": s["url"], "title": s["title"], "published_at": s["published_at"]}
                        for s in seg.get("sources", [])],
            "audio": a["file"] if a else None, "duration_sec": a["duration_sec"] if a else 0,
            "sound": seg.get("sound"),
        })
    local_regions = sorted({s["block"].split(":", 1)[1] for s in segs if s["block"].startswith("local:")})
    return {
        "date": approved["date"],
        "title": f"BRIEF — {approved['date']}",
        "published_at": iso(now_utc()),
        "approved": True,  # the reviewer's identity stays in approved.json, not in the public file
        "script_sha256": approved["script_sha256"],
        "voice": {"provider": render["provider"], "voice": render["voice"]},
        "sonic": {"intro": "audio/intro.mp3", "bumper": "audio/bumper.mp3", "outro": "audio/outro.mp3"},
        "full_audio": render["full"]["file"], "duration_sec": render["full"]["duration_sec"],
        "regions": [{"id": r, "name": regions.get(r, r)} for r in local_regions],
        "segments": segs,
    }


def publish(date, allow_mock=False):
    approved, render = validate(date, allow_mock)
    edition = public_edition(approved, render)
    path = EDITIONS / date / "edition.json"
    write_json(path, edition)
    index = load_json(EDITIONS / "index.json", {"editions": []})
    index["editions"] = sorted({*index["editions"], date}, reverse=True)
    write_json(EDITIONS / "index.json", index)
    # latest.json is written last: readers see either the old or the complete new edition
    write_json(EDITIONS / "latest.json", {"date": date, "edition": f"editions/{date}/edition.json",
                                          "published_at": edition["published_at"]})
    shutil.copyfile(ROOT / render["full"]["file"], ROOT / "audio" / "daily.mp3")  # legacy player path
    return path
