"""Regional source registry built from the official Recommended Media Map.

`sync_map` takes a snapshot of https://map.detector.media/ (IMI + Detector Media):
the same public endpoint the map page itself calls when a visitor clicks a region.
`discover_feeds` checks each outlet's website for a public RSS/Atom feed.

Nothing is added to the pipeline unless it is on the official map; a source without
a working public feed stays in the registry with feed_status "not-found".
"""
import concurrent.futures as cf
import html
import json
import re
import time
import urllib.parse

from . import http
from .normalize import url_host
from .util import ROOT, config, load_json, write_json

MAP_URL = "https://map.detector.media/"
AJAX_URL = "https://map.detector.media/wp-admin/admin-ajax.php"
REGISTRY = ROOT / "config" / "media_map.json"
FEED_PATHS = ["/feed", "/rss", "/rss.xml", "/feed.xml", "/rss/all.xml", "/uk/rss", "/news/rss"]


def parse_map_areas(page_html):
    return re.findall(r'<g data-tippy-content="([^"]+)" data-ids="([^"]*)"', page_html)


def parse_area_items(fragment, area_label):
    out = []
    blocks = re.split(r'<div class="_aside-info-item _aside-info-item-\d+" data-media="', fragment)[1:]
    for b in blocks:
        mid = b.split('"', 1)[0]
        name = re.search(r"_aside-info-item__title[^>]*>\s*<span>(.*?)</span>", b, re.S)
        kind = re.search(r'_aside-info-item__label">\s*<span>(.*?)</span>', b, re.S)
        links = [u for u in re.findall(r'data-href="([^"]+)"', b) if "goo.gl" not in u and "google." not in u]
        scope = re.search(r'data-tippy-content="(Національний|Регіональний|Місцевий|Гіперлокальний)"', b)
        out.append({
            "map_id": int(mid),
            "name": html.unescape(name.group(1)).replace("\xa0", " ").strip() if name else None,
            "type": kind.group(1).strip() if kind else None,
            "url": links[0] if links else None,
            "scope": scope.group(1) if scope else None,
            "map_region": area_label,
        })
    return out


def sync_map(fetch=http.fetch, pause=0.5):
    regions = {r["map_label"]: r["id"] for r in config("regions.json")["regions"]}
    page = fetch(MAP_URL).decode("utf-8", "replace")
    areas = parse_map_areas(page)
    if not areas:
        raise RuntimeError("map page structure changed: no regions found")
    old = {e["map_id"]: e for e in (load_json(REGISTRY, {}) or {}).get("media", [])}
    media = []
    for label, ids in areas:
        body = urllib.parse.urlencode({"action": "map_area_details", "area_label": label, "post_ids": ids}).encode()
        data = json.loads(fetch(AJAX_URL, data=body).decode("utf-8"))
        items = parse_area_items(data.get("html", ""), label)
        expected = len([i for i in ids.split(",") if i])
        if len(items) != expected:
            raise RuntimeError(f"{label}: expected {expected} outlets, parsed {len(items)}")
        for it in items:
            it["region"] = regions.get(label)
            prev = old.get(it["map_id"], {})
            for k in ("feeds", "feed_status", "feed_checked_on", "notes", "content_signals"):
                if k in prev:
                    it[k] = prev[k]
            media.append(it)
        time.sleep(pause)
    return media


def _looks_like_feed(body: bytes):
    head = body[:4000].decode("utf-8", "replace")
    return bool(re.search(r"<(rss|feed|rdf:RDF)[\s>]", head))


def discover_feed(site_url, fetch=http.fetch):
    """Return (feed_url | None, note). Checks <link rel=alternate> first, then common paths."""
    if not site_url:
        return None, "no website on the map"
    try:
        page = fetch(site_url, retries=1, timeout=20).decode("utf-8", "replace")
    except http.FetchError as e:
        return None, f"website: {e}"
    cands = []
    for tag in re.findall(r"<link[^>]+>", page):
        if re.search(r"application/(rss|atom)\+xml", tag):
            h = re.search(r"href=[\"']([^\"']+)", tag)
            if h:
                cands.append(urllib.parse.urljoin(site_url, html.unescape(h.group(1))))
    # plain links such as <a href=".../rss/...xml">RSS</a>
    for h in re.findall(r"href=[\"']([^\"']*(?:rss|feed)[^\"']*)[\"']", page, flags=re.I):
        if not re.search(r"(facebook|twitter|t\.me|telegram|feedly|google)\.", h):
            cands.append(urllib.parse.urljoin(site_url, html.unescape(h)))
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(site_url))
    cands += [base + p for p in FEED_PATHS]
    host = url_host(site_url)
    seen = set()
    for c in cands:
        if c in seen or "comments" in c:
            continue
        seen.add(c)
        # Only feeds on the outlet's own domain (or its subdomain/parent) count.
        h = url_host(c)
        if not (h == host or h.endswith("." + host) or host.endswith("." + h)):
            continue
        try:
            body = fetch(c, retries=0, timeout=20)
        except http.FetchError:
            continue
        if _looks_like_feed(body) and re.search(rb"<(item|entry)[\s>]", body):
            return c, "ok"
    return None, "no public feed found"


def content_signals(site_url, fetch=http.fetch):
    """robots.txt Content-Signal directives (e.g. ai-input=no), recorded for policy review."""
    base = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(site_url))
    try:
        txt = fetch(base + "/robots.txt", retries=0, timeout=15).decode("utf-8", "replace")
    except http.FetchError:
        return {}
    out = {}
    for line in txt.splitlines():
        m = re.match(r"\s*content-signal\s*:\s*(.+)", line, flags=re.I)
        if m:
            for part in re.split(r"[,\s]+", m.group(1).strip()):
                if "=" in part:
                    k, v = part.split("=", 1)
                    out[k.strip().lower()] = v.strip().lower()
    return out


def discover_feeds(media, today, fetch=http.fetch, workers=8, only_missing=False):
    todo = [m for m in media if not (only_missing and m.get("feed_status") == "active")]
    by_site = {}
    for m in todo:
        by_site.setdefault(m.get("url"), []).append(m)
    def probe(u):
        feed, note = discover_feed(u, fetch)
        return feed, note, (content_signals(u, fetch) if u else {})

    with cf.ThreadPoolExecutor(workers) as ex:
        results = dict(zip(by_site, ex.map(probe, by_site)))
    for site, entries in by_site.items():
        feed, note, signals = results[site]
        for m in entries:
            m["content_signals"] = signals
            m["feeds"] = [feed] if feed else []
            m["feed_status"] = "active" if feed else ("blocked" if "HTTP 403" in note else "not-found")
            m["feed_checked_on"] = today
            m["notes"] = "" if feed else note
    return media


def save(media, today):
    lists = config("sources.json")["lists"]["media_map"]
    write_json(REGISTRY, {
        "version": 1,
        "source": MAP_URL,
        "edition": lists["edition"],
        "snapshot_on": today,
        "count": len(media),
        "note": "Знімок офіційної Мапи рекомендованих медіа. Не редагувати вручну: оновлюється `python -m brief registry`.",
        "media": sorted(media, key=lambda m: (m.get("region") or "", m["name"] or "")),
    })


def regional_sources():
    """Regional outlets with a verified feed, in the same shape as national sources."""
    reg = load_json(REGISTRY, {}) or {}
    out, seen_feeds = [], set()
    for m in reg.get("media", []):
        if m.get("feed_status") != "active" or not m.get("feeds"):
            continue
        feed = m["feeds"][0]
        if feed in seen_feeds:  # several map entries can share one site (e.g. Суспільне region pages)
            continue
        seen_feeds.add(feed)
        out.append({
            "id": f"map-{m['map_id']}",
            "name": m["name"],
            "homepage": m["url"],
            "domains": sorted({url_host(m["url"]), url_host(feed)}),
            "feeds": m["feeds"],
            "geography": "regional",
            "region": m.get("region"),
            "list": "media_map",
            "feed_status": "active",
            "content_signals": m.get("content_signals", {}),
        })
    return out
