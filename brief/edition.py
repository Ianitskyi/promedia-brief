"""Stage 5: build the edition draft (exact script + fact trace) for editorial review.

The script is *extractive*: every story sentence is the lead sentence(s) of a source
publication's own annotation, prefixed by an explicit attribution. Nothing is
paraphrased or generated, so the script cannot contain words the sources did not
publish. Editors may shorten or rewrite sentences on the review page; the edited
text is re-checked against the same evidence before approval.
"""
import datetime as dt
import re

from . import cluster as clus
from .classify import detect_places, excluded, primary_region, topics
from .collect import load_pool
from .factcheck import check_sentence
from .normalize import content_stems, split_sentences
from .score import factors, importance
from .speech import date_words, load_lexicon, speech_text, speech_warnings
from .util import KYIV, ROOT, config, iso, kyiv_date, load_json, now_utc, sha256_text, write_json, write_text

EDITIONS = ROOT / "editions"
PLURAL_SOURCES = {"Тексти", "Ґрати"}


def edition_end(date, now=None):
    now = now or now_utc()
    end_of_day = dt.datetime.fromisoformat(date).replace(hour=23, minute=59, tzinfo=KYIV)
    return min(now, end_of_day.astimezone(dt.timezone.utc))


def load_items(date, end, hours):
    prev = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
    items = load_pool(prev)["items"] + load_pool(date)["items"]
    by_id = {}
    for it in items:
        by_id.setdefault(it["id"], it)
    return clus.window(list(by_id.values()), end, hours)


def previous_titles(date):
    prev = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
    d = load_json(EDITIONS / prev / "draft.json", None)
    if not d:
        return []
    return [s["title"] for s in d["segments"] if s["kind"] == "story"]


def _source_order():
    cfg = config("sources.json")
    return {s["id"]: i for i, s in enumerate(cfg["national_sources"])}


def attribution(source_name, templates):
    t = templates["attribution"][1]  # "{source} повідомляє: " — keeps the lead's own capitalisation
    if source_name in PLURAL_SOURCES:
        t = t.replace("повідомляє", "повідомляють")
    return t.format(source=spoken_name(source_name, templates))


def spoken_name(name, templates):
    """Short on-air name: "Zaholovok.com.ua (Закарпаття. Про головне)" -> "Zaholovok.com.ua"."""
    name = templates.get("spoken_names", {}).get(name, name)
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()


def spoken_list(names, limit=3):
    if len(names) <= limit:
        return ", ".join(names)
    rest = len(names) - limit
    word = "видання" if rest % 10 in (2, 3, 4) and rest % 100 not in (12, 13, 14) else "видань"
    if rest % 10 == 1 and rest % 100 != 11:
        word = "видання"
    return ", ".join(names[:limit]) + f" та ще {rest} {word}"


# Sentences opening like this depend on context the listener does not have.
DEPENDENT_OPENINGS = ("в результаті", "у результаті", "згодом", "йдеться", "за словами", "також", "при цьому",
                      "водночас", "це ", "цей ", "ця ", "ці ", "він ", "вона ", "вони ", "там ", "тоді ", "крім того",
                      "окрім того", "зокрема", "натомість", "однак", "проте", "але ", "тож ", "отже", "тому ",
                      "у нього", "у неї", "його ", "її ", "їх ", "серед них", "з них")
BACKGROUND_OPENINGS = ("нагадаємо", "як повідомлялося", "раніше ", "як відомо", "читайте", "дивіться", "фото:", "відео:",
                       "про це ")  # "Про це йдеться у пресрелізі..., пише ..." only restates attribution


def _sentence(s):
    s = s.replace("\u200b", "").strip()
    return s if s[-1:] in ".!…»\"" else s + "."


def headline_sentence(title):
    """A headline usable as a spoken sentence, or None.

    Rejected: questions, very short headlines and label-style headlines such as
    "Reuters: ..." or "Прем'єр Норвегії: ..." whose first part only names a speaker.
    """
    t = re.sub(r"\s*\((оновлено|онлайн|фото|відео|фото, відео|інфографіка)\)\s*$", "", title.replace("\u200b", ""), flags=re.I).strip()
    if len(t.split()) < 4 or t.endswith("?"):
        return None
    if ":" in t:
        label = t.split(":", 1)[0].split()
        # "Reuters:", "Прем'єр Норвегії:" name a speaker; "Росіяни обстріляли Херсон:" is a sentence
        if len(label) <= 2 or (len(label) == 3 and all(w[:1].isupper() for w in label)):
            return None
    return _sentence(t)


def _too_similar(a, b):
    sa, sb = set(content_stems(a)), set(content_stems(b))
    return bool(sa) and len(sa & sb) / len(sa | sb) > 0.5


def lead_sentences(item, max_sentences, max_words):
    """Headline (if speakable) + annotation sentences that add information, within budget."""
    head = headline_sentence(item["title"])
    if not head:
        # Annotations usually continue the headline ("...район міста") and are not
        # understandable alone, so a story without a speakable headline is skipped.
        return []
    out, words = [head], len(head.split())
    for s in split_sentences(item.get("description", "")):
        low = s.lower()
        n = len(s.split())
        if n < 5 or s.endswith("?") or low.startswith(BACKGROUND_OPENINGS):
            continue
        if not re.match(r"[«\"„“(]?[А-ЯІЇЄҐA-Z0-9]", s):  # fragment: ", який відповідає ..."
            continue
        if s.count("«") != s.count("»") or s.count('"') % 2:  # cut inside a quotation
            continue
        if _too_similar(s, head):
            continue
        if out and words + n > max_words:
            break
        out.append(_sentence(s))
        words += n
        if len(out) >= max_sentences:
            break
    return out


def pick_representative(members, order):
    def key(m):
        lead = split_sentences(m.get("description", ""))
        informative = sum(len(s.split()) for s in lead[:2])
        speakable = headline_sentence(m["title"]) is not None
        return (not speakable, m.get("geography") != "national", -min(informative, 50), order.get(m["source_id"], 99))

    return sorted(members, key=key)[0]


def build_story(cl, items_by_id, ed_cfg, templates, sensitive_cfg, lexicon, order, year=None, region=None, gaz=None):
    members = [items_by_id[i] for i in cl["item_ids"]]
    pool = members
    if region:
        # In a regional block the spoken headline itself must name the region.
        pool = [m for m in members if region in detect_places(m["title"], gaz)]
        if not pool:
            return None, "no headline names the region"
    rep = pick_representative(pool, order)
    leads = lead_sentences(rep, ed_cfg["max_sentences_per_story"], ed_cfg["max_words_per_story"])
    if not leads:
        return None, "headline is not speakable (question, label-style or too short)"
    evidence = {m["id"]: f"{m['title']}. {m.get('description', '')}" for m in members}
    sentences = []
    for i, lead in enumerate(leads):
        prefix = attribution(rep["source"], templates) if i == 0 else ""
        trace = check_sentence(lead, evidence, cl["independent_sources"], sensitive_cfg, year)
        text = prefix + lead
        sentences.append({
            "id": f"{cl['id']}-s{i + 1}",
            "kind": "fact",
            "attribution": rep["source"] if prefix else None,
            "attribution_text": prefix,
            "body": lead,
            "text": text,
            "original_text": text,
            "speech_text": speech_text(text, lexicon),
            "speech_warnings": speech_warnings(speech_text(text, lexicon)),
            "from_item": rep["id"],
            **trace,
            "editor_confirmed": False,
        })
    # national outlets first, then regional; alphabetical inside each group
    geo = {m["source"]: m.get("geography") for m in members}
    others = sorted({m["source"] for m in members} - {rep["source"]}, key=lambda n: (geo[n] != "national", n))
    if others:
        names = spoken_list([spoken_name(o, templates) for o in others])
        text = templates["also_reported"].format(sources=names)
        sentences.append({
            "id": f"{cl['id']}-s{len(sentences) + 1}", "kind": "coverage", "text": text, "original_text": text,
            "speech_text": speech_text(text, lexicon), "status": "verified", "claims": [
                {"type": "coverage", "value": s, "found_in": [m["id"] for m in members if m["source"] == s]}
                for s in others], "reasons": [], "sensitive": [], "editor_confirmed": False,
        })
    return {
        "title": rep["title"],
        "sentences": sentences,
        "sources": [{"item_id": m["id"], "name": m["source"], "url": m["url"], "title": m["title"],
                     "published_at": m.get("published_at")} for m in sorted(members, key=lambda m: m.get("published_at") or "")],
        "evidence": evidence,
    }, None


def template_segment(seg_id, kind, block, lines, lexicon, **extra):
    sentences = [{"id": f"{seg_id}-s{i + 1}", "kind": "template", "text": t, "original_text": t,
                  "speech_text": speech_text(t, lexicon),
                  "status": "verified", "claims": [], "reasons": [], "sensitive": [], "editor_confirmed": False}
                 for i, t in enumerate(lines)]
    return {"id": seg_id, "kind": kind, "block": block, "sentences": sentences, **extra}


def build(date, now=None):
    now = now or now_utc()
    ed = config("editorial.json")
    regions_cfg = config("regions.json")
    region_names = {r["id"]: r["name"] for r in regions_cfg["regions"]}
    gaz = clus.gazetteer_from_config(regions_cfg)
    ed_cfg, templates, scoring = ed["edition"], ed["templates"], ed["scoring"]
    lexicon = load_lexicon()
    order = _source_order()
    end = edition_end(date, now)

    items = load_items(date, end, ed_cfg["window_hours"])
    log = {"items_in_window": len(items), "excluded": [], "deduplicated": []}
    kept = []
    for it in items:
        why = excluded(it, ed["exclude"])
        if why:
            log["excluded"].append({"id": it["id"], "title": it["title"], "reason": why})
        else:
            kept.append(it)
    kept, removed = clus.dedupe(kept)
    log["deduplicated"] = removed
    items_by_id = {it["id"]: it for it in kept}
    clusters = clus.cluster(kept, ed["clustering"], gaz)
    log["clusters"] = len(clusters)
    log["multi_source_clusters"] = sum(1 for c in clusters if c["independent_sources"] > 1)

    prev = previous_titles(date)
    for c in clusters:
        members = [items_by_id[i] for i in c["item_ids"]]
        text = " ".join(f"{m['title']}. {m.get('description', '')}" for m in members)
        c["topics"] = topics(text, ed["topics"])
        c["primary_region"] = primary_region(members, gaz)
        if c["primary_region"]:
            share = sum(1 for m in members if c["primary_region"] in detect_places(
                f"{m['title']}. {m.get('description', '')}", gaz)) / len(members)
            if share < 0.5:  # a national story that one regional outlet localised
                c["primary_region"] = None
        others = sorted(set(detect_places(text, gaz)) - {c["primary_region"]})
        c["regions"] = ([c["primary_region"]] if c["primary_region"] else []) + others
        c["has_national_source"] = any(m.get("geography") == "national" for m in members)
        f = factors(c, items_by_id, end, scoring, None, prev)
        c["score_breakdown"] = f
        c["score"] = importance(f, scoring["weights"])

    story_cache, skipped = {}, []

    def story_for(c, region=None):
        key = (c["id"], region)
        if key not in story_cache:
            story_cache[key] = build_story(c, items_by_id, ed_cfg, templates, ed["sensitive"], lexicon, order,
                                           int(date[:4]), region, gaz)
        return story_cache[key]

    def take(cands, n, block, region=None, per_region=None, used=(), prior=()):
        picked, counts = [], {}
        for c in cands:
            if len(picked) >= n:
                break
            if c["id"] in used:
                continue
            dup = next((p for p, _ in list(prior) + picked if clus.likely_same_event(c, p, items_by_id)), None)
            if dup:
                skipped.append({"cluster": c["id"], "block": block, "reason": f"possible duplicate of {dup['id']}"})
                continue
            key = c.get("primary_region")
            if per_region and key and counts.get(key, 0) >= per_region:
                continue
            story, why = story_for(c, c.get("primary_region") if block != "national" else None)
            if story is None:
                skipped.append({"cluster": c["id"], "block": block, "reason": why})
                continue
            if any(s["status"] == "unsupported" for s in story["sentences"]):
                skipped.append({"cluster": c["id"], "block": block, "reason": "unsupported claims"})
                continue
            counts[key] = counts.get(key, 0) + 1
            picked.append((c, story))
        return picked

    national = take(sorted((c for c in clusters if c["has_national_source"]), key=lambda c: -c["score"]),
                    ed_cfg["national_stories"], "national")
    used = {c["id"] for c, _ in national}
    roundup = take(sorted((c for c in clusters if c["primary_region"] and c["id"] not in used),
                          key=lambda c: -c["score"]), ed_cfg["regional_roundup_stories"], "regional",
                   per_region=ed_cfg["regional_roundup_max_per_region"], prior=national)
    local = {}
    for r in ed_cfg["pilot_regions"]:
        cands = []
        for c in clusters:
            if c["primary_region"] == r and c["id"] not in used:
                f = factors(c, items_by_id, end, scoring, r, prev)
                cands.append((importance(f, scoring["weights"]), f, c))
        cands.sort(key=lambda x: -x[0])
        picked = take([dict(c, score=s, score_breakdown=f) for s, f, c in cands], ed_cfg["local_stories_per_region"],
                      f"local:{r}", prior=national)
        local[r] = picked

    words = date_words(date)
    segs = [template_segment("intro", "intro", "intro",
                             [t.format(date_words=words) for t in templates["intro"]], lexicon)]
    segs.append(template_segment("national-heading", "heading", "national", [templates["national_heading"]], lexicon))

    def story_segment(c, story, block, rank, region=None, must=False):
        return {"id": f"{block}-{c['id']}".replace(":", "-"), "kind": "story", "block": block, "region": region,
                "rank": rank, "cluster_id": c["id"], "title": story["title"], "topics": c["topics"],
                "regions": c["regions"], "score": c["score"], "score_breakdown": c["score_breakdown"],
                "independent_sources": c["independent_sources"], "must_include": must,
                "sentences": story["sentences"], "sources": story["sources"], "include": True}

    evidence = {}
    for i, (c, s) in enumerate(national):
        segs.append(story_segment(c, s, "national", i + 1, must=i < ed_cfg["must_include_national"]))
        evidence.update(s["evidence"])
    segs.append({"id": "transition", "kind": "transition", "block": "transition", "sentences": [], "sound": "bumper"})
    segs.append(template_segment("regional-heading", "heading", "regional", [templates["regional_heading"]], lexicon))
    for i, (c, s) in enumerate(roundup):
        segs.append(story_segment(c, s, "regional", i + 1))
        evidence.update(s["evidence"])
    for r, picked in local.items():
        if not picked:
            continue
        segs.append(template_segment(f"local-{r}-heading", "heading", f"local:{r}",
                                     [templates["local_heading"].format(region_name=region_names[r])], lexicon, region=r))
        for i, (c, s) in enumerate(picked):
            segs.append(story_segment(c, s, f"local:{r}", i + 1, region=r))
            evidence.update(s["evidence"])
    segs.append(template_segment("outro", "outro", "outro", [t.format(date_words=words) for t in templates["outro"]], lexicon))

    sentences = [s for seg in segs for s in seg["sentences"]]
    draft = {
        "date": date,
        "status": "draft",
        "generated_at": iso(now),
        "window_end": iso(end),
        "config_status": ed["status"],
        "pipeline": "brief 0.2 extractive",
        "segments": segs,
        "evidence": evidence,
        "log": {**log, "skipped": skipped,
                "candidates": [{"cluster": c["id"], "score": c["score"], "sources": c["sources"],
                                "regions": c["regions"], "title": items_by_id[c["item_ids"][0]]["title"]}
                               for c in sorted(clusters, key=lambda c: -c["score"])[:40]]},
        "stats": {
            "stories": sum(1 for s in segs if s["kind"] == "story"),
            "sentences": len(sentences),
            "needs_review": sum(1 for s in sentences if s["status"] == "needs_review"),
            "unsupported": sum(1 for s in sentences if s["status"] == "unsupported"),
            "excluded": len(log["excluded"]),
            "characters": sum(len(s["speech_text"]) for s in sentences),
        },
    }
    draft["script_sha256"] = script_hash(draft)
    return draft


def script_text(draft, block_filter=None):
    lines = []
    for seg in draft["segments"]:
        if seg["kind"] == "story" and not seg.get("include", True):
            continue
        if block_filter and not block_filter(seg):
            continue
        if seg["kind"] == "transition":
            lines.append("[ЗВУКОВИЙ ПЕРЕХІД]")
        for s in seg["sentences"]:
            lines.append(s["text"])
    return "\n".join(lines)


def script_hash(draft):
    return sha256_text(script_text(draft))


def render_markdown(draft):
    out = [f"# BRIEF — чернетка випуску за {draft['date']}", "",
           f"Статус: **{draft['status']}** · згенеровано {draft['generated_at']} · sha256 `{draft['script_sha256'][:12]}`", "",
           "> Чернетка для редакційної перевірки. Не публікувати без затвердження.", ""]
    for seg in draft["segments"]:
        if seg["kind"] == "transition":
            out += ["", "**[ЗВУКОВИЙ ПЕРЕХІД]**", ""]
            continue
        if seg["kind"] == "story":
            out.append(f"### {seg['block']} #{seg['rank']} · score {seg['score']} · {', '.join(seg['topics'])}"
                       + (" · обов'язкова" if seg.get("must_include") else ""))
        for s in seg["sentences"]:
            mark = {"verified": "✓", "needs_review": "⚠", "unsupported": "✗"}.get(s["status"], "")
            out.append(f"{mark} {s['text']}")
            for r in s.get("reasons", []):
                out.append(f"  - {r}")
        if seg["kind"] == "story":
            out.append("")
            for src in seg["sources"]:
                out.append(f"  - [{src['name']}]({src['url']}) — {src['title']}")
            out.append("")
    return "\n".join(out) + "\n"


def build_and_save(date, now=None):
    draft = build(date, now)
    path = EDITIONS / date / "draft.json"
    write_json(path, draft)
    write_text(EDITIONS / date / "draft.md", render_markdown(draft))
    idx = load_json(EDITIONS / "drafts.json", {"drafts": []})
    idx["drafts"] = sorted({*idx["drafts"], date}, reverse=True)[:30]
    write_json(EDITIONS / "drafts.json", idx)
    return path, draft


def today():
    return kyiv_date(now_utc())
