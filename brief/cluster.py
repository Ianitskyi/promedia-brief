"""Stage 2: deduplication and event clustering.

* Exact duplicates (same canonical URL) are removed.
* Near duplicates from the *same* outlet (republished with a new URL) are merged.
* Reports by different outlets about the same event form one cluster; all source
  links are kept and the number of independent outlets becomes a ranking signal.

Guard rails against merging *different* events that merely share vocabulary:
  - publication times must be close (max_time_gap_hours);
  - the pair must share anchors (numbers, proper names, places), not just common words
    such as "обстріл" or "уряд"; the fewer anchors shared, the higher the text similarity
    required (config: clustering.tiers);
  - if both items name places and none of the places overlap, they are not merged;
  - if both items contain numbers and none overlap, similarity must be very high;
  - a new item joins a cluster only if it is compatible with no veto against any member.
"""
import datetime as dt
import math
import re
from collections import Counter

from .classify import detect_places
from .normalize import WORD, canonical_url, content_stems, norm_word, numbers, stem
from .util import from_iso

GENERIC_CAPS = {"україна", "україни", "україні", "україну", "росія", "росії", "рф", "зсу", "сили", "президент",
                "уряд", "кабмін", "верховна", "рада", "ради", "мзс", "сша", "єс"}


def item_text(it):
    return f"{it.get('title', '')}. {it.get('description', '')}"


def proper_noun_stems(texts, gazetteer=None):
    """Stems of words seen capitalised in a non-initial position anywhere in the corpus.

    Lets "Зеленський" count as a name even when it opens a headline. Place names are
    excluded here because places are compared separately (and must not count twice).
    """
    out = set()
    for text in texts:
        prev = "."
        for m in WORD.finditer(text):
            w = m.group(0)
            if (w[:1].isupper() and prev not in ".!?:" and len(w) > 2 and norm_word(w) not in GENERIC_CAPS
                    and not (gazetteer and detect_places(w, gazetteer))):
                out.add(stem(w))
            tail = text[m.end():m.end() + 2].strip()
            prev = tail[:1] if tail else ""
    return out


def anchors(text, names=None):
    """Numbers + proper-name stems: the specifics that distinguish one event from another.

    Calendar numbers ("20 жовтня", "2026") are left out: every report of the day has them.
    """
    calendar = set(re.findall(r"(?<!\d)(\d{1,2})\s+(?:січ|лют|берез|квіт|трав|черв|лип|серп|верес|жовт|листоп|груд)\w*", text))
    calendar |= set(re.findall(r"(?<!\d)((?:19|20)\d\d)(?!\d)", text))
    out = set(numbers(text)) - calendar
    first = True
    for m in WORD.finditer(text):
        w = m.group(0)
        st = stem(w)
        if names is not None:
            if w[:1].isupper() and st in names:
                out.add(st)
        elif w[:1].isupper() and not first and norm_word(w) not in GENERIC_CAPS and len(w) > 2:
            out.add(st)
        tail = text[m.end():m.end() + 2].strip()
        first = tail[:1] in (".", "!", "?", ":") if tail else False
    return out


def places(text, gazetteer):
    return detect_places(text, gazetteer)


def dedupe(items):
    """Remove exact URL duplicates and same-source republications. Returns (items, removed)."""
    seen_url, seen_title, out, removed = set(), {}, [], []
    for it in sorted(items, key=lambda x: x.get("published_at") or ""):
        url = canonical_url(it["url"])
        if url in seen_url:
            removed.append({"id": it["id"], "reason": "duplicate-url"})
            continue
        key = (it["source_id"], " ".join(content_stems(it["title"])))
        if key in seen_title:
            removed.append({"id": it["id"], "reason": "same-source-duplicate", "kept": seen_title[key]})
            continue
        seen_url.add(url)
        seen_title[key] = it["id"]
        out.append(it)
    return out, removed


class Vectorizer:
    def __init__(self, docs):
        self.df = Counter()
        for d in docs:
            self.df.update(set(d))
        self.n = max(1, len(docs))

    def vec(self, stems):
        tf = Counter(stems)
        v = {t: c * math.log(1 + self.n / self.df.get(t, 1)) for t, c in tf.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {t: x / norm for t, x in v.items()}


def cosine(a, b):
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


def _hours(a, b):
    ta, tb = from_iso(a.get("published_at")), from_iso(b.get("published_at"))
    if not ta or not tb:
        return 0.0
    return abs((ta - tb).total_seconds()) / 3600


def compatible(a, b, sim, cfg):
    if _hours(a, b) > cfg["max_time_gap_hours"]:
        return False, "time-gap"
    pa, pb = a["_places"], b["_places"]
    if pa and pb and not (pa & pb):
        return False, "different-places"
    shared = len(a["_anchors"] & b["_anchors"]) + len(pa & pb)
    if a.get("source_id") == b.get("source_id") and sim < cfg["same_source_min_similarity"]:
        return False, "same-source-different-story"  # a local outlet's many stories about its own city
    na, nb = a["_anchors"] & set(numbers(a["_text"])), b["_anchors"] & set(numbers(b["_text"]))
    if na and nb and not (na & nb) and sim < cfg["different_numbers_min_similarity"]:
        return False, "different-numbers"
    # Tiers: the more specifics (names, numbers, places) two reports share, the less
    # wording overlap is needed. Shared common words alone never suffice.
    for tier in cfg["tiers"]:
        if shared >= tier["min_shared_anchors"] and sim >= tier["min_similarity"]:
            return True, f"tier {tier['min_shared_anchors']}/{tier['min_similarity']}"
    return False, "too-few-anchors" if shared < cfg["tiers"][-1]["min_shared_anchors"] else "similarity"


def cluster(items, cfg, gazetteer):
    """Greedy average-link clustering in chronological order. Deterministic."""
    docs = []
    names = proper_noun_stems((item_text(it) for it in items), gazetteer)
    for it in items:
        it["_text"] = item_text(it)
        it["_stems"] = content_stems(it["_text"])
        it["_anchors"] = anchors(it["_text"], names)
        it["_places"] = places(it["_text"], gazetteer)
        docs.append(it["_stems"])
    vz = Vectorizer(docs)
    for it in items:
        it["_vec"] = vz.vec(it["_stems"])

    clusters = []
    vetoes = {"time-gap", "different-places"}
    for it in sorted(items, key=lambda x: (x.get("published_at") or "", x["id"])):
        best, best_sim = None, 0.0
        for c in clusters:
            checks = []
            for m in c["members"]:
                s = cosine(it["_vec"], m["_vec"])
                checks.append((s,) + compatible(it, m, s, cfg))
            if any(reason in vetoes for _, _, reason in checks):
                continue
            avg = sum(s for s, _, _ in checks) / len(checks)
            if any(ok for _, ok, _ in checks) and avg >= cfg["min_average_similarity"] and avg > best_sim:
                best, best_sim = c, avg
        if best is not None:
            best["members"].append(it)
        else:
            clusters.append({"members": [it]})

    out = []
    for c in clusters:
        members = c["members"]
        ids = sorted(m["id"] for m in members)
        out.append({
            "id": "c-" + ids[0],
            "item_ids": [m["id"] for m in members],
            "sources": sorted({m["source"] for m in members}),
            "independent_sources": len({m["source_id"] for m in members}),
            "first_published": min((m.get("published_at") or "") for m in members) or None,
            "last_published": max((m.get("published_at") or "") for m in members) or None,
            "places": sorted(set().union(*(m["_places"] for m in members))),
        })
    for it in items:
        for k in ("_text", "_stems", "_anchors", "_places", "_vec"):
            it.pop(k, None)
    return out


def gazetteer_from_config(regions_cfg):
    return {r["id"]: r["stems"] for r in regions_cfg["regions"]}


def window(items, end, hours):
    start = end - dt.timedelta(hours=hours)
    out = []
    for it in items:
        t = from_iso(it.get("published_at"))
        if t and start <= t <= end and "future-date" not in it.get("date_issues", []):
            out.append(it)
    return out


def likely_same_event(c1, c2, items_by_id, min_similarity=0.15):
    """Second-chance duplicate check at selection time (looser than clustering).

    Compares individual reports pairwise (comparing whole clusters would make a large
    cluster "match" everything). Used only to keep a possible repeat out of the
    edition; the skipped cluster is logged for the editor instead of being merged.
    """
    p1, p2 = set(c1.get("regions", [])[:1]), set(c2.get("regions", [])[:1])
    if p1 and p2 and not (p1 & p2):
        return False
    def prep(i):
        t = item_text(items_by_id[i])
        return set(content_stems(t)), anchors(t)
    m1 = [prep(i) for i in c1["item_ids"][:12]]
    m2 = [prep(i) for i in c2["item_ids"][:12]]
    for s1, a1 in m1:
        for s2, a2 in m2:
            if not s1 or not s2:
                continue
            jacc = len(s1 & s2) / len(s1 | s2)
            shared = len(a1 & a2) + len(p1 & p2)
            if (jacc >= min_similarity and shared >= 1) or (jacc >= 0.1 and shared >= 2):
                return True
    return False
