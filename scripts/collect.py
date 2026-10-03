#!/usr/bin/env python3
import datetime as dt
import json
import pathlib
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config" / "sources.json").read_text(encoding="utf-8"))
UA = "BRIEF-by-ProMedia/0.1 (+https://github.com/Ianitskyi/promedia-brief)"

def text(node, tag):
    el = node.find(tag)
    return (el.text or "").strip() if el is not None and el.text else ""

def parse_feed(source):
    req = urllib.request.Request(source["feed"], headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
    root = ET.fromstring(raw)
    rows = []

    # RSS 2.x
    for item in root.findall(".//item"):
        title = text(item, "title")
        link = text(item, "link")
        description = text(item, "description")
        pub = text(item, "pubDate")
        published = None
        if pub:
            try:
                published = parsedate_to_datetime(pub).isoformat()
            except Exception:
                published = pub
        if title and link:
            rows.append({
                "source": source["name"],
                "title": title,
                "url": link,
                "published_at": published,
                "description": description
            })

    # Atom fallback
    ns = {"a":"http://www.w3.org/2005/Atom"}
    if not rows:
        for entry in root.findall(".//a:entry", ns):
            title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip()
            link_el = entry.find("a:link", ns)
            link = link_el.get("href") if link_el is not None else ""
            published = entry.findtext("a:published", default="", namespaces=ns) or entry.findtext("a:updated", default="", namespaces=ns)
            summary = entry.findtext("a:summary", default="", namespaces=ns) or ""
            if title and link:
                rows.append({
                    "source": source["name"],
                    "title": title,
                    "url": link,
                    "published_at": published or None,
                    "description": summary.strip()
                })
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

    # Deduplicate URLs; newest occurrence wins.
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
