"""How much a story matters: how many people it touches, and how widely it is covered.

Owner, 2026-11-17, following standard news values (Galtung & Ruge 1965; Harcup & O'Neill 2001,
2017): the bigger the number of people affected and the longer the consequences, the more important
the story. One death is a tragedy for a family; a struck bridge in a city of millions changes the
lives of millions — and the edition must lead with that.

Two things are computed here, by the program, never by Claude:

* **related clusters** — clusters about the same subject (the Crimean bridge story arrives as ten clusters:
  «Аксьонов заявив…», «супутникові знімки…», «рух частково відновили…»). Two clusters belong to one
  subject when their headlines share a pair of rare words. Coverage is the number of different outlets
  across a cluster and its related clusters, and of related clusters only one enters the edition.
* **rarity** — how unusual the subject is: whether its main pair of headline words appeared day after
  day in the previous two weeks (routine) or not at all (unprecedented).
* **impact** — for a story about damage or disruption of something many people depend on (bridges,
  metro, power, water, heat, rail, ports), the population of the place it happens in, on a log scale,
  tempered by how many outlets confirm it. Populations are rough (order of magnitude is all that
  matters) and live in config/editorial.json → impact.
"""
import math
import re
from collections import Counter

from .normalize import content_stems


def _rare_stems(title, df, lo, hi):
    return {s for s in set(content_stems(title)) if lo <= df.get(s, 0) <= hi}


def _name_stems(title):
    words = re.findall(r"[\w'’ʼ-]+", title)
    return set(content_stems(" ".join(w for w in words[1:] if w[:1].isupper() and not w.isupper())))


def families(clusters, items_by_id, cfg, history=()):
    """Sets c["related"] (ids of clusters about the same subject) and c["coverage"] (outlets across them).

    Two clusters are related when their headlines share a pair of rare words that several headlines use
    together («Кримськ… мост…», «Північн… Південн…»). Only direct neighbours count — no chains, so one
    common word can't glue the whole day into one subject."""
    titles = {i: items_by_id[i]["title"] for c in clusters for i in c["item_ids"]}
    stems_of = {i: set(content_stems(t)) for i, t in titles.items()}
    df = Counter(s for st in stems_of.values() for s in st)
    n = max(1, len(titles))
    lo, hi = cfg.get("family_min_items", 3), max(3, int(n * cfg.get("family_max_share", 0.04)))
    rare = {i: {s for s in st if lo <= df[s] <= hi} for i, st in stems_of.items()}
    # one word of the pair must be a name (a capitalised word inside the headline): «Кримськ…», «Північн…»
    names = {i: {s for s in rare[i] if s in _name_stems(t)} for i, t in titles.items()}
    pair_items = Counter()
    for i, st in rare.items():
        for a in names[i]:
            for b in st:
                if a != b:
                    pair_items[tuple(sorted((a, b)))] += 1
    by_pair, pairs_of = {}, {}
    for c in clusters:
        pairs = set()
        for i in c["item_ids"][:15]:
            pairs |= {tuple(sorted((a, b))) for a in names[i] for b in rare[i]
                      if a != b and pair_items[tuple(sorted((a, b)))] >= lo}
        pairs_of[c["id"]] = pairs
        for pr in pairs:
            by_pair.setdefault(pr, set()).add(c["id"])
    by_id = {c["id"]: c for c in clusters}
    # Unexpectedness (Galtung & Ruge): how often the subject's main pair of words made several headlines
    # a day in the previous days. The Crimean bridge: 0 of 14 days → rare; «загинув … Херсонщина»: daily.
    for c in clusters:
        top, top_name = Counter(), Counter()
        for i in c["item_ids"]:
            st = rare[i]
            top.update(tuple(sorted((a, b))) for a in names[i] for b in st if a != b)
            top_name.update(names[i])
        c["topic_name"] = top_name.most_common(1)[0][0] if top_name else None
        best = top.most_common(1)
        if not best or best[0][1] < cfg.get("rarity_min_items", 5) or not history:
            c["rarity"], c["topic_pair"] = 0.5, (list(best[0][0]) if best else None)
            continue
        a, b = best[0][0]
        seen = [d for d, day in history if sum(1 for st in day if a in st and b in st) >= 2]
        c["rarity"] = round(1 - min(1.0, len(seen) / cfg.get("rarity_routine_days", 7)), 3)
        c["topic_pair"] = [a, b]
    for c in clusters:
        related = set()
        for pr in pairs_of[c["id"]]:
            ids = by_pair[pr]
            if len(ids) <= cfg.get("family_max_clusters", 40):
                related |= ids
        related.discard(c["id"])
        c["related"] = sorted(related)
        outlets = {items_by_id[i]["source_id"] for i in c["item_ids"]}
        for r in related:
            outlets |= {items_by_id[i]["source_id"] for i in by_id[r]["item_ids"]}
        c["coverage"] = len(outlets)
        times = [items_by_id[i].get("published_at") for r in related for i in by_id[r]["item_ids"]]
        c["newest_related"] = max(filter(None, times), default=None)


def _has(text, markers):
    return any(re.search(r"(?<![\w'’])" + re.escape(m), text) for m in markers)


def impact(text, regions, coverage, cfg):
    """0..1: how many people a disruption touches; 0 when the story is not about such a disruption."""
    low = text.lower().replace("’", "'").replace("ʼ", "'")
    if not (_has(low, cfg["infrastructure_markers"]) and _has(low, cfg["disruption_markers"])):
        return 0.0
    pops = [cfg["population"].get(r, 0) for r in regions]
    pop = max(pops) if pops and max(pops) else cfg.get("unknown_place_population", 300_000)
    lo, hi = math.log10(cfg.get("population_floor", 10_000)), math.log10(cfg.get("population_ceiling", 5_000_000))
    scale = min(1.0, max(0.0, (math.log10(pop) - lo) / (hi - lo)))
    confirmed = min(1.0, coverage / cfg.get("coverage_for_full_impact", 5))
    # routine (outage schedules) touches many people but is not news of the day by itself
    routine = cfg.get("routine_factor", 0.5) if _has(low, cfg.get("routine_markers", [])) else 1.0
    return round(scale * confirmed * routine, 3)


def coverage_factor(n, saturation):
    """Outlets that reported the subject, on a log scale: 1 → 0, saturation and more → 1."""
    if n <= 1:
        return 0.0
    return round(min(1.0, math.log(n) / math.log(saturation)), 3)
