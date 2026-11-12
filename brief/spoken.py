"""Daily spoken edition: the approved stories retold in plain radio language, then checked.

The approved edition (approved.json) is built from sentences copied from the sources. That is
safe but reads like a wire feed. Here Claude retells each story the way a newsreader would
(like the hand-made 29 October edition), and every retelling is checked against the stored
evidence of that story, the same claim check the draft goes through:

* every number, name, quote and month or weekday in the text must occur in the evidence;
* no relative time words (сьогодні, вчора...): the edition can be heard on another day;
* stories merged into one must not add up their figures (no totals, see
  docs/THEMATIC_NEWS_AND_TEASERS.md).

A story that fails is read from its approved (verbatim) sentences instead, so a bad
retelling never reaches the audio. Without ANTHROPIC_API_KEY the whole edition is read from
the approved sentences. The length is cut to the day's share of the monthly TTS budget
(data/tts-usage.json), lowest-ranked stories first.

Output: editions/<date>/spoken.json, same segment shape as approved.json, with its own
sha256 and the sha256 of the approved text it was made from.
"""
import calendar
import json
import os
import re

from . import tts
from .edition import EDITIONS, script_hash, script_text
from .factcheck import extract_claims, _found
from .review import load_approved
from .speech import date_words, load_lexicon
from .util import ROOT, config, iso, load_json, now_utc, write_json

USAGE = ROOT / "data" / "tts-usage.json"
RELATIVE_TIME = re.compile(r"(?<![\w'’])(сьогодні|сьогоднішн\w*|вчора|учора|вчорашн\w*|завтра|завтрашн\w*|"
                           r"позавчора|минулої ночі|цієї ночі|цього ранку|нині)(?![\w'’])", re.I)
TOTALS = re.compile(r"(?<![\w'’])(загалом|усього|всього|сумарно|у сумі|разом)(?![\w'’])", re.I)
MAX_STORY_CHARS = 600

SYSTEM = """Ти — редактор українського аудіовипуску новин BRIEF. Ти переказуєш новини для диктора: \
простою розмовною українською, як у радіоефірі. Слухач чує текст один раз, тому речення короткі, \
перше речення сюжету — суть новини.

Правила точності (порушення будь-якого = сюжет не вийде в ефір):
1. Використовуй ЛИШЕ факти з наданих текстів джерел цього сюжету. Нічого не додавай від себе, \
навіть загальновідомого.
2. Числа пиши цифрами точно як у джерелі. Не округлюй, не перераховуй, не додавай числа з різних \
повідомлень, не пиши загальних підсумків («загалом», «усього», «разом»).
3. Імена, назви, посади, цитати — лише ті, що є в джерелі цього сюжету.
4. Не вживай відносних слів часу: «сьогодні», «вчора», «завтра», «цієї ночі», «нині». Дату чи \
день тижня називай лише якщо вони є в джерелі.
5. Якщо джерело посилається на когось («за даними Повітряних сил», «як повідомив Лубінець»), \
збережи це посилання. Назви медіа, яке опублікувало новину, не називай.
6. Не оцінюй, не коментуй, без сенсаційності.

Стиль: 2–4 речення на сюжет. Сюжети про одну подію чи тему (наприклад, наслідки одного обстрілу \
в різних містах) можна об'єднати в один, перелічивши місця, — але без підсумкових чисел.

Приклад гарного сюжету (стиль, не факти):
«Чотирнадцять людей загинули в Дніпрі внаслідок російського удару дроном по залізничному вокзалу. \
Понад десять людей поранені. Безпілотник влучив у платформу, де стояв електропоїзд до Запоріжжя.»

Також напиши teaser: перелік двох-трьох головних тем випуску через кому, без чисел і подробиць, \
з малої літери, наприклад: «наслідки російських обстрілів, рішення Нацбанку щодо облікової ставки \
та графіки відключень світла». Для кожного сюжету дай короткий заголовок з 1–3 слів."""

SCHEMA = {
    "type": "object",
    "properties": {
        "teaser": {"type": "string"},
        "stories": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "story_ids": {"type": "array", "items": {"type": "string"}},
                "title": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["story_ids", "title", "text"],
            "additionalProperties": False,
        }},
    },
    "required": ["teaser", "stories"],
    "additionalProperties": False,
}


def settings():
    return config("editorial.json").get("daily", {})


# --- budget -------------------------------------------------------------------------------

def day_budget(date, cfg=None, usage=None):
    """Characters this edition may send to the paid voice: the rest of the month's credits
    (minus a reserve) shared evenly between the days left, today included."""
    cfg = cfg or settings()
    usage = usage if usage is not None else load_json(USAGE, {})
    y, m, d = (int(x) for x in date.split("-"))
    month = f"{y:04d}-{m:02d}"
    used = usage.get(month, {}).get("characters", 0)
    credits = cfg.get("monthly_credits", 30000) * (1 - cfg.get("reserve", 0.1))
    left = credits / cfg.get("credits_per_char", 1.0) - used
    days_left = calendar.monthrange(y, m)[1] - d + 1
    return max(0, int(left / days_left))


def record_usage(date, characters, provider):
    usage = load_json(USAGE, {})
    month = usage.setdefault(date[:7], {"characters": 0, "editions": {}})
    previous = month["editions"].get(date, {}).get("characters", 0)
    month["characters"] += characters - previous  # a re-render of the same day replaces its count
    month["editions"][date] = {"characters": characters, "provider": provider}
    write_json(USAGE, usage)
    return month["characters"]


# --- checks -------------------------------------------------------------------------------

def check_text(text, evidence, merged=False):
    """Problems with a retold story; empty list = it may be read."""
    problems = []
    for c in extract_claims(text):
        if not any(_found(c, ev) for ev in evidence.values()):
            problems.append(f"не знайдено в джерелах: {c['type']} «{c['value']}»")
    if RELATIVE_TIME.search(text):
        problems.append(f"відносне слово часу: «{RELATIVE_TIME.search(text).group(0)}»")
    if merged and TOTALS.search(text):
        problems.append("об'єднаний сюжет із підсумковим словом — можливе додавання чисел")
    if len(text) > MAX_STORY_CHARS:
        problems.append(f"задовгий сюжет ({len(text)} символів)")
    return problems


def check_teaser(teaser, evidence):
    if not teaser or re.search(r"\d", teaser) or RELATIVE_TIME.search(teaser) or len(teaser) > 200:
        return False
    return all(any(_found(c, ev) for ev in evidence.values())
               for c in extract_claims(teaser) if c["type"] in ("name", "quote"))


def sentences_of(text):
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", text.strip()) if s.strip()]


# --- Claude -------------------------------------------------------------------------------

def story_evidence(seg, evidence):
    return {src["item_id"]: evidence[src["item_id"]] for src in seg["sources"] if src["item_id"] in evidence}


def request_text(date, stories, evidence, budget):
    lines = [f"Дата випуску: {date}. Обсяг усіх сюжетів разом — не більше {budget} символів; "
             "якщо всі не вміщаються, залиш найважливіші (вони йдуть першими).", ""]
    for seg in stories:
        lines.append(f"### Сюжет {seg['id']} (важливість {seg['rank']}, блок {seg['block']})")
        for iid, txt in story_evidence(seg, evidence).items():
            lines.append(f"Джерело {iid}: {txt}")
        lines.append("")
    return "\n".join(lines)


def ask_claude(date, stories, evidence, budget, model):
    import anthropic

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": request_text(date, stories, evidence, budget)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError(f"Claude declined ({getattr(response.stop_details, 'category', None)})")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude's answer was cut off (max_tokens)")
    text = next(b.text for b in response.content if b.type == "text")
    usage = response.usage
    return json.loads(text), {"model": response.model, "input_tokens": usage.input_tokens,
                              "output_tokens": usage.output_tokens, "request_id": response._request_id}


# --- build --------------------------------------------------------------------------------

def _segment(seg_id, kind, block, lines, title=None, sources=None):
    return {"id": seg_id, "kind": kind, "block": block, "title": title, "include": True,
            "sentences": [{"id": f"{seg_id}-s{i + 1}", "kind": kind, "text": t} for i, t in enumerate(lines)],
            "sources": sources or []}


def build(date, use_llm=True, budget=None, provider_name=None):
    cfg = settings()
    approved = load_approved(date)
    evidence = approved["evidence"]
    stories = [seg for seg in approved["segments"] if seg["kind"] == "story"
               and seg["block"] in cfg.get("blocks", ["national", "regional"])]
    stories.sort(key=lambda s: (s["block"] != "national", s["rank"]))
    budget = day_budget(date, cfg) if budget is None else budget
    by_id = {s["id"]: s for s in stories}

    retold, log = [], {"llm": None, "rejected": [], "fallback": []}
    if use_llm and os.environ.get("ANTHROPIC_API_KEY") and stories:
        try:
            answer, log["llm"] = ask_claude(date, stories, evidence, max(300, budget - 150),
                                            cfg.get("llm_model", "claude-opus-5-5"))
        except Exception as e:  # the edition still goes out, read from the approved sentences
            log["llm_error"] = f"{type(e).__name__}: {e}"
            answer = None
    else:
        answer = None
        log["llm_error"] = "no ANTHROPIC_API_KEY" if use_llm else "disabled"

    used = set()
    teaser = None
    if answer:
        for st in answer["stories"]:
            ids = [i for i in st["story_ids"] if i in by_id and i not in used]
            if not ids or len(ids) != len(st["story_ids"]):
                log["rejected"].append({"story_ids": st["story_ids"], "problems": ["невідомий або повторний сюжет"]})
                continue
            ev = {}
            for i in ids:
                ev.update(story_evidence(by_id[i], evidence))
            problems = check_text(st["text"], ev, merged=len(ids) > 1)
            if problems:
                log["rejected"].append({"story_ids": ids, "text": st["text"], "problems": problems})
                continue
            used.update(ids)
            sources = [src for i in ids for src in by_id[i]["sources"]]
            retold.append({"ids": ids, "title": st["title"].strip(" ."), "lines": sentences_of(st["text"]),
                           "sources": sources, "rank": min(stories.index(by_id[i]) for i in ids), "retold": True})
        teaser = answer["teaser"].strip(" .") or None
    # Stories whose retelling failed the check (or all of them, without Claude): read from their
    # approved, verbatim sentences. Stories Claude left out to keep the edition short stay out.
    rejected = {i for r in log["rejected"] for i in r["story_ids"]}
    for seg in stories:
        if seg["id"] in used or (answer and seg["id"] not in rejected):
            continue
        lines = [s["text"] for s in seg["sentences"]]
        if RELATIVE_TIME.search(" ".join(lines)):  # «сьогодні» in the source is wrong a day later
            log.setdefault("dropped_relative_time", []).append(seg["id"])
            continue
        retold.append({"ids": [seg["id"]], "title": seg.get("title"), "lines": lines,
                       "sources": seg["sources"], "rank": stories.index(seg), "retold": False})
        if answer:
            log["fallback"].append(seg["id"])
    if answer:
        log["left_out"] = [seg["id"] for seg in stories if seg["id"] not in used and seg["id"] not in rejected]
    retold.sort(key=lambda r: r["rank"])

    words = date_words(date)
    outro_line = cfg.get("outro", "Це був BRIEF за {date_words}. Посилання на першоджерела — на сайті BRIEF.") \
        .format(date_words=words)

    def assemble(items, teaser):
        intro_line = f"Це BRIEF. Головне за {words}" + (f": {teaser}." if teaser else ".")
        segs = [_segment("intro", "intro", "intro", [intro_line])]
        for n, r in enumerate(items, 1):
            segs.append(_segment(f"story-{n}", "story", "national", r["lines"], title=r["title"], sources=r["sources"]))
            segs[-1]["retold"] = r["retold"]
            segs[-1]["from_stories"] = r["ids"]
        segs.append(_segment("outro", "outro", "outro", [outro_line]))
        return segs

    # Fit the day's budget, measured the way the paid voice will be charged (numbers spelled out).
    provider = tts.get(provider_name or cfg.get("tts_provider", "elevenlabs"))
    from .render import plan

    lexicon = load_lexicon()

    def characters(segs):
        return sum(len(c) for seg in plan({"segments": segs}, provider, lexicon)
                   for s in seg["sentences"] for c in s["chunks"])

    items = list(retold)
    segs = assemble(items, teaser)
    while len(items) > cfg.get("min_stories", 2) and characters(segs) > budget:
        items.pop()
        segs = assemble(items, teaser)
    log["cut_for_budget"] = [r["ids"] for r in retold[len(items):]]
    # The teaser may only name what the edition really contains (after the cut).
    in_edition = {}
    for r in items:
        for i in r["ids"]:
            in_edition.update(story_evidence(by_id[i], evidence))
    if teaser and not check_teaser(teaser, in_edition):
        log["teaser_rejected"] = teaser
        segs = assemble(items, None)

    spoken = {
        "date": date,
        "kind": "spoken",
        "made_at": iso(now_utc()),
        "approved_sha256": approved["script_sha256"],
        "approved_by": approved["approved_by"],
        "segments": segs,
        "evidence": evidence,
        "budget_characters": budget,
        "characters": characters(segs),
        "stories": len(items),
        "retold": sum(1 for r in items if r["retold"]),
        "log": log,
    }
    spoken["script_sha256"] = script_hash(spoken)
    spoken["script_text"] = script_text(spoken)
    write_json(EDITIONS / date / "spoken.json", spoken)
    return spoken
