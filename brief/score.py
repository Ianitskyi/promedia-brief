"""Stage 4: transparent importance score.

importance = Σ weight_f × factor_f, every factor in [0, 1]; weights in config/editorial.json.
The breakdown is stored next to each story so editors can see *why* it ranked where it did.
Popularity signals (views, clicks, shares) are deliberately not used.
"""
import math

from .textmatch import has_marker
from .util import from_iso


def _tiered(text, tiers):
    best = 0.0
    for level, markers in tiers.items():
        if any(has_marker(text, m) for m in markers):
            best = max(best, float(level))
    return best


def factors(cluster, items_by_id, now, scoring, target_region=None, previous_titles=()):
    members = [items_by_id[i] for i in cluster["item_ids"]]
    text = " ".join(f"{m['title']}. {m.get('description', '')}" for m in members)

    n = cluster["independent_sources"]
    confirmations = min(1.0, (n - 1) / max(1, scoring["confirmations_saturation"] - 1))

    newest = max((from_iso(m["published_at"]) for m in members if m.get("published_at")), default=None)
    age_h = max(0.0, (now - newest).total_seconds() / 3600) if newest else 24.0
    recency = math.pow(0.5, age_h / scoring["recency_half_life_hours"])

    geographies = {m.get("geography") for m in members}
    regions = {cluster.get("primary_region")} - {None}
    if target_region is None:  # national block
        geo = 1.0 if "national" in geographies else 0.4
        if "national" in geographies and "regional" in geographies:
            geo = 1.0
    else:
        geo = 1.0 if target_region in regions else 0.0

    novelty = 1.0
    if previous_titles:
        from .normalize import content_stems

        mine = set(content_stems(members[0]["title"]))
        for t in previous_titles:
            other = set(content_stems(t))
            if mine and len(mine & other) / len(mine | other) > 0.6:
                novelty = 0.3
                break

    return {
        "confirmations": round(confirmations, 3),
        "public_significance": _tiered(text, scoring["public_significance_markers"]),
        "scale": _tiered(text, scoring["scale_markers"]),
        "recency": round(recency, 3),
        "geographic_relevance": geo,
        "novelty": novelty,
    }


def importance(f, weights):
    return round(sum(weights[k] * f[k] for k in weights), 4)
