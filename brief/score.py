"""Stage 4: transparent importance score.

importance = Σ weight_f × factor_f, every factor in [0, 1]; weights in config/editorial.json.
The breakdown is stored next to each story so editors can see *why* it ranked where it did.
Popularity signals (views, clicks, shares) are deliberately not used.
"""
import math
import re

from .textmatch import has_marker
from .util import from_iso


def _tiered(text, tiers):
    best = 0.0
    for level, markers in tiers.items():
        if any(has_marker(text, m) for m in markers):
            best = max(best, float(level))
    return best


NUM_WORDS = {"один": 1, "одна": 1, "одного": 1, "одну": 1, "двоє": 2, "два": 2, "дві": 2, "двох": 2, "троє": 3,
             "три": 3, "трьох": 3, "четверо": 4, "чотири": 4, "чотирьох": 4, "п'ятеро": 5, "п'ять": 5, "шестеро": 6,
             "шість": 6, "семеро": 7, "сім": 7, "восьмеро": 8, "вісім": 8, "дев'ятеро": 9, "дев'ять": 9,
             "десятеро": 10, "десять": 10, "десятки": 20, "десятків": 20, "сотні": 100, "сотень": 100}
_N = r"(\d+|" + "|".join(sorted(map(re.escape, NUM_WORDS), key=len, reverse=True)) + r")"
KILLED = r"(?:загиб|загин|вбит|вбил|жертв|смертельн)"
INJURED = r"(?:поранен|постражд|травмован|госпіталізован)"


def _num(tok):
    tok = tok.replace("’", "'").replace("ʼ", "'")
    return int(tok) if tok.isdigit() else NUM_WORDS.get(tok, 0)


def casualties(text):
    """(killed, injured) reported in the text: the largest numbers next to the keywords.

    "загинули троє", "21 людина постраждала", "є загиблі" (= at least 1). A rough reading:
    it ranks stories, it never writes anything into the script.
    """
    low = text.lower().replace("’", "'").replace("ʼ", "'")
    result = []
    for kw in (KILLED, INJURED):
        best = 0
        for m in re.finditer(_N + r"\s+(?:[\w'–—-]+\s+){0,2}?" + kw, low):
            best = max(best, _num(m.group(1)))
        for m in re.finditer(kw + r"[\w'-]*\s+(?:[\w'-]+\s+){0,1}?" + _N + r"(?![\w-])", low):
            best = max(best, _num(m.group(1)))
        if not best and re.search(r"(?:є|наявні)\s+" + kw, low):
            best = 1
        result.append(min(best, 10000))
    return tuple(result)


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

    killed, injured = casualties(text)
    severity = killed * scoring.get("casualty_killed_weight", 3) + injured
    casualty = min(1.0, math.log1p(severity) / math.log1p(scoring.get("casualty_saturation", 60)))

    return {
        "casualties": round(casualty, 3),
        "confirmations": round(confirmations, 3),
        "public_significance": _tiered(text, scoring["public_significance_markers"]),
        "reach": _tiered(text, scoring["reach_markers"]),
        "recency": round(recency, 3),
        "geographic_relevance": geo,
        "novelty": novelty,
    }


def importance(f, weights):
    return round(sum(weights[k] * f[k] for k in weights), 4)
