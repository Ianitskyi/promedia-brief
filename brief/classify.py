"""Stage 3: topic and geography classification (transparent keyword rules)."""
import functools
import re

from .normalize import WORD, norm_word
from .textmatch import count_markers, has_marker


@functools.lru_cache(maxsize=64)
def _compile_gazetteer(items):
    exact, prefixes = {}, []
    for region_id, stems in items:
        for s in stems:
            if s.startswith("="):
                exact[s[1:]] = region_id
            else:
                prefixes.append((s, region_id))
    prefixes.sort(key=lambda x: -len(x[0]))
    return exact, tuple(prefixes)


def detect_places(text, gazetteer):
    """Region ids mentioned in the text. Only capitalised words count (proper names)."""
    exact, prefixes = _compile_gazetteer(tuple((k, tuple(v)) for k, v in sorted(gazetteer.items())))
    found = set()
    words = [(m.group(0), m.start()) for m in WORD.finditer(text or "")]
    for i, (w, _) in enumerate(words):
        if not w[:1].isupper():
            continue
        low = norm_word(w)
        if low in exact:
            found.add(exact[low])
            continue
        # multi-word stems such as "біла церкв" look at the next word too
        two = low + " " + norm_word(words[i + 1][0]) if i + 1 < len(words) else low
        for s, region_id in prefixes:
            if two.startswith(s) or low.startswith(s):
                found.add(region_id)
                break
    return found


def topics(text, topic_cfg, limit=2):
    scored = [(count_markers(text, kws), name) for name, kws in topic_cfg.items()]
    scored = [x for x in scored if x[0] > 0]
    scored.sort(key=lambda x: (-x[0], list(topic_cfg).index(x[1])))
    return [name for _, name in scored[:limit]] or ["Суспільство"]


def excluded(item, exclude_cfg):
    title = item.get("title", "").lower()
    for m in exclude_cfg["title_markers"]:
        if has_marker(title, m):
            return f"title marker: {m}"
    for m in exclude_cfg["url_markers"]:
        if m in item.get("url", ""):
            return f"url marker: {m}"
    return None


def is_sensitive(text, sensitive_cfg):
    low = text.lower()
    return [p for p in sensitive_cfg["patterns"] if re.search(r"(?<![\w'’])" + re.escape(p), low)]


def primary_region(members, gazetteer):
    """The region a story is *about*, or None.

    Weighted vote: a region named in a headline counts 3, in an annotation 1, and the
    home region of a regional outlet 1. A region must be named in at least one headline;
    otherwise incidental mentions (a street named after Хмельницький, a national story
    retold by a regional outlet) would pull the story into the wrong regional block.
    """
    votes, in_title = {}, set()
    for m in members:
        t = detect_places(m.get("title", ""), gazetteer)
        in_title |= t
        for r in t:
            votes[r] = votes.get(r, 0) + 3
        for r in detect_places(m.get("description", ""), gazetteer):
            votes[r] = votes.get(r, 0) + 1
        if m.get("geography") == "regional" and m.get("source_region"):
            votes[m["source_region"]] = votes.get(m["source_region"], 0) + 1
    cands = [(v, r) for r, v in votes.items() if r in in_title]
    if not cands:
        return None
    cands.sort(key=lambda x: (-x[0], x[1]))
    return cands[0][1]
