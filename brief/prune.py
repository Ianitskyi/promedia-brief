"""Retention: delete whole editions (audio, text, sources, drafts) older than N days (default 7).

The indexes (index.json, drafts.json, latest.json) are updated so no page points to a
deleted edition. If the latest published edition is itself older than N days it is
deleted too and the site falls back to its placeholder until the next edition.
"""
import datetime as dt
import shutil

from .edition import EDITIONS
from .util import kyiv_date, load_json, now_utc, write_json


def prune(keep_days=7, now=None):
    now = now or now_utc()
    cutoff = (dt.date.fromisoformat(kyiv_date(now)) - dt.timedelta(days=keep_days)).isoformat()
    removed = []
    if not EDITIONS.exists():
        return removed
    for d in sorted(p for p in EDITIONS.iterdir() if p.is_dir()):
        try:
            dt.date.fromisoformat(d.name)
        except ValueError:
            continue
        if d.name < cutoff:
            shutil.rmtree(d)
            removed.append(d.name)
    if not removed:
        return removed
    gone = set(removed)
    for name, key in (("index.json", "editions"), ("drafts.json", "drafts")):
        idx = load_json(EDITIONS / name)
        if idx:
            idx[key] = [x for x in idx.get(key, []) if x not in gone]
            write_json(EDITIONS / name, idx)
    latest = load_json(EDITIONS / "latest.json")
    if latest and latest.get("date") in gone:
        (EDITIONS / "latest.json").unlink()
    return removed
