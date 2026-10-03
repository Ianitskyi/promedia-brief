#!/usr/bin/env python3
import datetime as dt
import json
import pathlib
import feedparser

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8"))

def parse_feed(source):
    feed = feedparser.parse(source["feed"])
    rows = []
    for entry in feed.entries:
        title = (entry.get("title") or "").strip()
        link = (entry.get("link") or "").strip()
        summary = (entry.get("summary") or entry.get("description") or "").strip()
        published = entry.get("published") or entry.get("updated") or None
        if title and link:
            rows.append({
                "source": source["name"],
                "title": title,
                "url": link,
                "published_at": published,
                "description": summary
            })
    if getattr(feed, "bozo", 0) and not rows:
        raise RuntimeError(str(getattr(feed, "bozo_exception", "feed parse error")))
    return rows

def main():
    now = dt.datetime.now(dt.timezone.utc)
    collected = []
    errors = []
    for source in CONFIG["national_sources"]:
        if source.get("status") != "active" or not source.get("feed"):
            continue
        try:
            collected.extend(parse_feed(source))
        except Exception as e:
            errors.append({"source":source["name"], "error":str(e)})

    by_url = {x["url"]: x for x in collected}
    out = {
        "generated_at": now.isoformat(),
        "source_count": len({x["source"] for x in by_url.values()}),
        "item_count": len(by_url),
        "items": list(by_url.values()),
        "errors": errors
    }
    path = ROOT / "data" / "raw" / (now.date().isoformat() + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(path)
    print(f"{out['item_count']} items from {out['source_count']} sources; {len(errors)} errors")

if __name__ == "__main__":
    main()
