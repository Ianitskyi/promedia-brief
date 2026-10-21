"""Stage 1: collect RSS items from eligible sources into data/raw/<Kyiv date>.json.

The daily pool is *merged*, not overwritten: every scheduled run adds new items and
keeps the ones collected earlier that day, so the pool survives feed truncation
(most feeds expose only the latest 20-100 entries).
"""
import concurrent.futures as cf
import datetime as dt

import feedparser

from . import http
from .normalize import canonical_url, clean_text, host_matches, item_id, parse_date
from .registry import regional_sources
from .util import ROOT, config, iso, kyiv_date, load_json, now_utc, write_json

RAW_DIR = ROOT / "data" / "raw"
SUMMARY_LIMIT = 600  # store an annotation, never the full article text
FUTURE_TOLERANCE = dt.timedelta(minutes=30)


def eligible_sources(cfg=None, include_regional=True):
    cfg = cfg or config("sources.json")
    out = [s for s in cfg["national_sources"] if s.get("feed_status") == "active" and s.get("feeds")]
    if include_regional:
        out += regional_sources()
    return out


def _truncate(s, limit=SUMMARY_LIMIT):
    if len(s) <= limit:
        return s
    cut = s[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > limit // 3 else cut.rsplit(" ", 1)[0] + "…"


def normalize_entry(entry, source, fetched_at):
    title = clean_text(entry.get("title"))
    link = (entry.get("link") or "").strip()
    if not title or not link:
        return None, "missing title or link"
    if not link.startswith("http"):
        return None, "relative link"
    if source.get("domains") and not host_matches(link, source["domains"]):
        return None, "link outside source domain"
    # Prefer the annotation; ignore content:encoded (full text) on purpose.
    summary = clean_text(entry.get("summary") or entry.get("description") or "")
    if summary.startswith(title):
        summary = summary[len(title):].lstrip(" .:-–—")
    raw_date = entry.get("published") or entry.get("updated")
    published = parse_date(raw_date)
    issues = []
    if published is None:
        issues.append("no-date")
    elif published > fetched_at + FUTURE_TOLERANCE:
        issues.append("future-date")
    tags = [clean_text(t.get("term")) for t in entry.get("tags", []) if t.get("term")]
    return {
        "id": item_id(link),
        "source_id": source["id"],
        "source": source["name"],
        "geography": source.get("geography", "national"),
        "source_region": source.get("region"),
        "url": canonical_url(link),
        "title": title,
        "published_at": iso(published),
        "published_raw": raw_date,
        "fetched_at": iso(fetched_at),
        "description": _truncate(summary),
        "categories": tags[:5],
        "date_issues": issues,
        "content_signals": source.get("content_signals") or {},
        "status": "new",
    }, None


def parse_feed(body, source, fetched_at):
    feed = feedparser.parse(body)
    rows, skipped = [], {}
    for e in feed.entries:
        row, why = normalize_entry(e, source, fetched_at)
        if row:
            rows.append(row)
        else:
            skipped[why] = skipped.get(why, 0) + 1
    if not rows and getattr(feed, "bozo", 0):
        raise RuntimeError(f"feed parse error: {getattr(feed, 'bozo_exception', '')}")
    return rows, skipped


def collect_source(source, fetched_at, fetch=http.fetch):
    rows, errors, skipped = [], [], {}
    for url in source["feeds"]:
        try:
            r, s = parse_feed(fetch(url), source, fetched_at)
            rows += r
            for k, v in s.items():
                skipped[k] = skipped.get(k, 0) + v
        except Exception as e:  # one broken feed must not stop the run
            errors.append({"source": source["name"], "feed": url, "error": str(e)[:300]})
    return rows, errors, skipped


def upgrade_legacy(item):
    """Items written by the first collector had no id / normalised date."""
    if "id" in item:
        return item
    published = parse_date(item.get("published_at"))
    names = {x["name"]: x["id"] for x in config("sources.json")["national_sources"]}
    item = dict(item)
    item.update({
        "id": item_id(item["url"]),
        "source_id": item.get("source_id") or names.get(item.get("source"), item.get("source")),
        "url": canonical_url(item["url"]),
        "published_raw": item.get("published_at"),
        "published_at": iso(published),
        "fetched_at": item.get("fetched_at"),
        "description": _truncate(clean_text(item.get("description", ""))),
        "geography": item.get("geography", "national"),
        "date_issues": [] if published else ["no-date"],
        "status": item.get("status", "new"),
    })
    return item


def merge_items(existing, new):
    """Union by id. The first sighting wins for fetched_at; later fields refresh text."""
    by_id = {}
    for it in existing:
        it = upgrade_legacy(it)
        by_id.setdefault(it["id"], it)
    added = 0
    for it in new:
        old = by_id.get(it["id"])
        if old is None:
            by_id[it["id"]] = it
            added += 1
        else:
            merged = dict(old)
            for k in ("title", "description", "published_at", "published_raw", "categories", "date_issues"):
                if it.get(k):
                    merged[k] = it[k]
            merged["fetched_at"] = old.get("fetched_at") or it["fetched_at"]
            by_id[it["id"]] = merged
    items = sorted(by_id.values(), key=lambda x: (x.get("published_at") or x.get("fetched_at") or ""), reverse=True)
    return items, added


def pool_path(date):
    return RAW_DIR / f"{date}.json"


def load_pool(date):
    data = load_json(pool_path(date), None) or {"items": []}
    data["items"] = [upgrade_legacy(i) for i in data.get("items", [])]
    return data


def run(fetch=http.fetch, now=None, sources=None, raw_dir=None, workers=8):
    now = now or now_utc()
    sources = sources if sources is not None else eligible_sources()
    collected, errors, skipped = [], [], {}
    with cf.ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(lambda s: collect_source(s, now, fetch), sources))
    for rows, errs, sk in results:
        collected += rows
        errors += errs
        for k, v in sk.items():
            skipped[k] = skipped.get(k, 0) + v

    # Route each item to the pool of its Kyiv publication date; keep only today and
    # yesterday so a feed that resurfaces old entries cannot rewrite history.
    today = kyiv_date(now)
    yesterday = kyiv_date(now - dt.timedelta(days=1))
    buckets = {today: [], yesterday: []}
    stale = 0
    for it in collected:
        d = kyiv_date(dt.datetime.fromisoformat(it["published_at"])) if it["published_at"] else today
        if d in buckets:
            buckets[d].append(it)
        else:
            stale += 1

    base = raw_dir or RAW_DIR
    report = {"generated_at": iso(now), "sources_attempted": len(sources), "errors": errors,
              "skipped": skipped, "stale": stale, "pools": {}}
    for date, items in buckets.items():
        path = base / f"{date}.json"
        if not items and not path.exists():
            continue
        data = load_json(path, None) or {"items": []}
        merged, added = merge_items(data.get("items", []), items)
        runs = (data.get("runs") or [])[-47:] + [{"at": iso(now), "fetched": len(items), "added": added, "errors": len(errors)}]
        out = {
            "date": date,
            "generated_at": iso(now),
            "source_count": len({x["source"] for x in merged}),
            "item_count": len(merged),
            "items": merged,
            "errors": errors if date == today else data.get("errors", []),
            "runs": runs,
        }
        write_json(path, out)
        report["pools"][date] = {"items": len(merged), "added": added}
    return report
