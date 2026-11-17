"""Daily digest of Russian strikes: many short casualty reports become one story.

Owner's decision (2026-11-15): instead of five to ten separate reports about strikes on
different towns, the edition opens with one summary story — «Унаслідок російських ударів за
добу загинули щонайменше N людей, ще щонайменше M людей поранено» — followed by a few
of the most important local details. That frees room for other subjects.

The sum is computed here, by the program, never by Claude, and only from figures that can be
traced to one clause of one source:

* an item counts only if it reports a Russian attack (attack + Russia markers), was published
  on the edition day or the day before, names no other calendar date, and names exactly one
  region of Ukraine (config/regions.json), so the same people can't land in two regions;
* a figure counts only if its clause (text between commas, full stops, «та») has a word for
  killed or for injured — not both — and exactly one number left after ages, hours, drones,
  rockets and the like are set aside; clauses about soldiers, Russian troops or longer periods
  («з початку року», «за тиждень», «загалом») are skipped;
* killed and injured are never added together;
* inside one region figures are never added (a regional summary usually repeats the city
  figures): the region gets the largest figure that two sources confirm; if none is confirmed
  twice and the reports disagree, the smallest; then the regions are added.

Any doubt makes the program skip that figure, so the result can only be lower than the truth,
never higher — that is why it is said with «щонайменше». Every component (region, number,
clause, source link) is stored in the segment («digest») so the calculation can be checked.
If fewer than two strike stories, or no verified figure at all, nothing is merged and the
stories stay as they are. See docs/THEMATIC_NEWS_AND_TEASERS.md.
"""
import datetime as dt
import re
from zoneinfo import ZoneInfo

from .classify import detect_places
from .util import config

KYIV = ZoneInfo("Europe/Kyiv")

ATTACK = re.compile(r"(удар|вдар|атак|обстріл|обстрілю|дрон|безпілот|ракет|шахед|каб\b|бомб|вибух|приліт|артилер)", re.I)
RUSSIA = re.compile(r"(рф|росі|російськ|ворог|ворож|окупант|агресор)", re.I)
KILLED = re.compile(r"(загину|загиб|загибл|вбит|вбив|убит|убив|смертельн|помер|забра\w* житт)", re.I)
INJURED = re.compile(r"(поранен|поранил|постражда|травмова|травмувал|травм|дістал\w* поранен|госпіталіз)", re.I)
# whose casualties these are not, or a longer period than a day
SKIP_CLAUSE = re.compile(r"(військов|бійц|захисник|солдат|окупант|росіян|загалом|усього|всього|з початку|"
                         r"від початку|за тиждень|за місяць|за рік|минулого|протягом тижня|з 20\d\d|"
                         r"повномасштабн|за весь час|ліквідов)", re.I)
MONTHS = ("січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня", "вересня",
          "жовтня", "листопада", "грудня")
DATE_IN_TEXT = re.compile(r"(\d{1,2})(?:-?го)?\s+(" + "|".join(MONTHS) + r")", re.I)

WORDS = {
    "один": 1, "одна": 1, "одного": 1, "одну": 1, "одне": 1, "одній": 1, "одному": 1,
    "два": 2, "дві": 2, "двоє": 2, "двох": 2, "двом": 2,
    "три": 3, "троє": 3, "трьох": 3, "чотири": 4, "четверо": 4, "чотирьох": 4,
    "п'ять": 5, "п'ятеро": 5, "п'ятьох": 5, "шість": 6, "шестеро": 6, "шістьох": 6, "шести": 6,
    "сім": 7, "семеро": 7, "сімох": 7, "семи": 7, "вісім": 8, "восьмеро": 8, "вісьмох": 8, "восьми": 8,
    "дев'ять": 9, "дев'ятеро": 9, "дев'ятьох": 9, "дев'яти": 9, "десять": 10, "десятеро": 10, "десятьох": 10,
    "десяти": 10, "одинадцять": 11, "дванадцять": 12, "тринадцять": 13, "чотирнадцять": 14,
    "п'ятнадцять": 15, "шістнадцять": 16, "сімнадцять": 17, "вісімнадцять": 18, "дев'ятнадцять": 19,
    "двадцять": 20,
}
# a number followed by one of these is not a count of people
NOT_PEOPLE = ("рок", "рік", "річ", "год", "хвил", "дрон", "ракет", "безпілот", "шахед", "км", "кілометр", "метр",
              "%", "відсот", "населен", "будин", "квартир", "авто", "машин", "грн", "раз", "област", "громад",
              "район", "поверх", "листопад", "жовт", "груд", "січ", "лют", "берез", "квіт", "трав", "черв",
              "лип", "серп", "верес", "тисяч", "млн", "мільйон", "кв", "га", "об'єкт", "обстріл", "атак", "удар",
              "снаряд", "бомб", "каб", "мін", "населених", "підприєм", "склад", "вагон", "потяг", "поїзд")
SINGULAR_KILLED = re.compile(r"\b(загинув|загинула|загиблий|загибла|вбито|убито|помер|померла)\b", re.I)
SINGULAR_INJURED = re.compile(r"\b(поранений|поранена|постраждав|постраждала|травмований|травмована|"
                              r"травмувався|травмувалася|дістав поранення|дістала поранення|отримав поранення|"
                              r"отримала поранення)\b", re.I)
# Daily round-ups («головне за 16 листопада») mix several events in one line, so a figure in them can
# land in the wrong region (17.11.2026: Komyshuvakha's 72 counted again for Crimea).
ROUNDUP = re.compile(r"(головне за|підсумки дня|підсумок дня|що відомо на ранок|що сталося за|новини дня|дайджест)", re.I)
# Not Russian strikes on Ukrainian-controlled territory: reports from occupied Crimea are about something else.
NOT_COUNTED_REGIONS = {"crimea"}
TOKEN = re.compile(r"[\w'’ʼ%-]+")

LOCATIVE = {
    "vinnytsia": "на Вінниччині", "volyn": "на Волині", "dnipropetrovsk": "на Дніпропетровщині",
    "donetsk": "на Донеччині", "zhytomyr": "на Житомирщині", "zakarpattia": "на Закарпатті",
    "zaporizhzhia": "на Запоріжжі", "ivano-frankivsk": "на Прикарпатті", "kyiv": "у Києві та області",
    "kirovohrad": "на Кіровоградщині", "luhansk": "на Луганщині", "lviv": "на Львівщині",
    "mykolaiv": "на Миколаївщині", "odesa": "на Одещині", "poltava": "на Полтавщині",
    "rivne": "на Рівненщині", "sumy": "на Сумщині", "ternopil": "на Тернопільщині",
    "kharkiv": "на Харківщині", "kherson": "на Херсонщині", "khmelnytskyi": "на Хмельниччині",
    "cherkasy": "на Черкащині", "chernivtsi": "на Буковині", "chernihiv": "на Чернігівщині", "crimea": "у Криму",
}


def gazetteer():
    return {r["id"]: r["stems"] for r in config("regions.json")["regions"]}


def _norm(text):
    return (text or "").replace("’", "'").replace("ʼ", "'")


def _number(token):
    t = token.lower()
    if re.fullmatch(r"\d{1,4}", t):
        return int(t)
    return WORDS.get(t)


def clause_figure(clause):
    """('killed'|'injured', n) for a clause that states one count of one kind, else None."""
    clause = _norm(clause)
    if SKIP_CLAUSE.search(clause):
        return None
    killed, injured = bool(KILLED.search(clause)), bool(INJURED.search(clause))
    if killed == injured:  # neither, or both in one clause: can't tell which number is which
        return None
    kind = "killed" if killed else "injured"
    tokens = TOKEN.findall(clause)
    numbers = []
    for i, tok in enumerate(tokens):
        n = _number(tok)
        if n is None or re.fullmatch(r"\d+-\w+", tok):  # «16-ї» is an hour or an ordinal
            continue
        after = [t.lower() for t in tokens[i + 1:i + 4]]
        # «42 і 45 років», «віком 55 років»: ages; «близько 14 населених пунктів»: not people
        if after and after[0].startswith(NOT_PEOPLE):
            continue
        if len(after) >= 3 and after[0] in ("і", "й", "та", "-", "–") and _number(after[1]) is not None \
                and after[2].startswith(NOT_PEOPLE):
            continue
        if i > 0 and tokens[i - 1].lower() in ("віком", "вік", "о", "об", "№", "номер"):
            continue
        numbers.append(n)
    if len(set(numbers)) > 1:
        return None
    if numbers:
        return kind, numbers[0]
    single = SINGULAR_KILLED if kind == "killed" else SINGULAR_INJURED
    return (kind, 1) if single.search(clause) else None


def clauses(text):
    parts = re.split(r"[.;:!?\n]|,|\s+—\s+|\s+та\s+|\s+а також\s+", _norm(text))
    return [p.strip() for p in parts if p.strip()]


def _local_date(iso_time):
    try:
        t = dt.datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return t.astimezone(KYIV).date()


def item_figures(text, published_at, date, gaz):
    """Verified figures of one source item, or None if the item can't be used."""
    day = dt.date.fromisoformat(date)
    allowed = {day, day - dt.timedelta(days=1)}
    if _local_date(published_at) not in allowed:
        return None, "опубліковано не за добу"
    if not (ATTACK.search(text) and RUSSIA.search(text)):
        return None, "не про російський удар"
    if ROUNDUP.search(_norm(text)):
        return None, "огляд кількох подій"
    for d, m in DATE_IN_TEXT.findall(_norm(text)):
        month = MONTHS.index(m.lower()) + 1
        if not any(x.month == month and x.day == int(d) for x in allowed):
            return None, f"інша дата в тексті: {d} {m}"
    regions = detect_places(text, gaz)
    if len(regions) != 1:
        return None, "регіон не визначено однозначно"
    region = next(iter(regions))
    if region in NOT_COUNTED_REGIONS:
        return None, "окупований Крим"
    found = {}
    for c in clauses(text):
        f = clause_figure(c)
        if f and f[1] > found.get(f[0], (0, ""))[0]:
            found[f[0]] = (f[1], c)
    if not found:
        return None, "немає однозначної цифри"
    return {"region": region, **found}, None


def is_strike_story(seg, evidence):
    text = " ".join([seg.get("title") or ""] + [s["text"] for s in seg.get("sentences", [])])
    text += " " + " ".join(evidence.get(src["item_id"], "") for src in seg.get("sources", []))
    if not (ATTACK.search(text) and RUSSIA.search(text)):
        return False
    return any(clause_figure(c) for c in clauses(text))


def pick(figures):
    """One figure for a region from all of its reports: the largest one confirmed by two
    sources; if no figure is confirmed twice and the reports disagree, the smallest."""
    sources = {}
    for f in figures:
        sources.setdefault(f["n"], set()).add(f["item_id"])
    confirmed = [n for n, s in sources.items() if len(s) >= 2]
    n = max(confirmed) if confirmed else min(sources)
    return next(f for f in figures if f["n"] == n), sorted(sources)


def tally(stories, evidence, date, max_killed=None):
    """One verified figure per region and kind, summed over regions. Returns (result, log).
    A report of more than max_killed dead is left out of the sum; its item ids are in result["big"]."""
    gaz = gazetteer()
    found, log, seen, big = {}, [], set(), set()
    for seg in stories:
        for src in seg.get("sources", []):
            text = evidence.get(src["item_id"])
            if not text or src["item_id"] in seen:
                continue
            seen.add(src["item_id"])
            figs, why = item_figures(text, src.get("published_at"), date, gaz)
            if not figs:
                log.append({"item_id": src["item_id"], "skipped": why})
                continue
            if max_killed is not None and figs.get("killed", (0,))[0] > max_killed:
                big.add(src["item_id"])
                log.append({"item_id": src["item_id"], "skipped": f"понад {max_killed} загиблих — окремий сюжет"})
                continue
            for kind in ("killed", "injured"):
                if kind in figs:
                    found.setdefault(figs["region"], {}).setdefault(kind, []).append(
                        {"n": figs[kind][0], "clause": figs[kind][1], "item_id": src["item_id"],
                         "source": src.get("name"), "url": src.get("url")})
    best = {}
    for region, kinds in found.items():
        for kind, figures in kinds.items():
            chosen, values = pick(figures)
            best.setdefault(region, {})[kind] = {**chosen, "reported": values}
    # The same number of people in two regions is far more likely one event counted twice than a
    # coincidence; any doubt lowers the sum (17.11.2026). Small figures (1–2) do repeat by chance.
    for kind in ("killed", "injured"):
        seen_n = {}
        for region in sorted(best):
            f = best[region].get(kind)
            if not f or f["n"] < 3:
                continue
            if f["n"] in seen_n:
                log.append({"item_id": f["item_id"], "skipped": f"та сама цифра ({f['n']}) вже є в іншій області: "
                                                                f"{seen_n[f['n']]}"})
                del best[region][kind]
            else:
                seen_n[f["n"]] = region
    best = {r: k for r, k in best.items() if k}
    killed = sum(r["killed"]["n"] for r in best.values() if "killed" in r)
    injured = sum(r["injured"]["n"] for r in best.values() if "injured" in r)
    return {"killed": killed, "injured": injured, "regions": best, "big": sorted(big)}, log


def _people(n, case="nom"):
    if n % 10 == 1 and n % 100 != 11:
        return "людина" if case == "nom" else "людину"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "людини"
    return "людей"


def lead_sentences(result, besides=False):
    """The summary sentences, built from the verified sum only. besides: a larger attack was told
    separately just before, so the sum starts with «Крім того» and says «в інших місцях»."""
    k, i, regions = result["killed"], result["injured"], result["regions"]
    out = []
    if k and i:
        verb = "загинула" if _people(k) == "людина" else "загинули"
        out.append(f"Унаслідок російських ударів за добу в Україні {verb} щонайменше {k} {_people(k)}, "
                   f"ще щонайменше {i} {_people(i, 'acc')} поранено.")
    elif k:
        verb = "загинула" if _people(k) == "людина" else "загинули"
        out.append(f"Унаслідок російських ударів за добу в Україні {verb} щонайменше {k} {_people(k)}.")
    elif i:
        out.append(f"Унаслідок російських ударів за добу в Україні поранено щонайменше {i} {_people(i, 'acc')}.")
    else:
        return []
    if besides:
        out[0] = out[0].replace("Унаслідок російських ударів за добу в Україні",
                                "Крім того, унаслідок інших російських ударів за добу в Україні", 1)
    weight = sorted(regions, key=lambda r: (-(regions[r].get("killed", {}).get("n", 0) * 10
                                              + regions[r].get("injured", {}).get("n", 0)), r))
    hit = [LOCATIVE[r] for r in weight if r in LOCATIVE][:2]
    if len(regions) >= 2 and hit:
        if len(hit) == 2 and hit[0].split()[0] == hit[1].split()[0]:  # «на Запоріжжі та Харківщині»
            hit[1] = hit[1].split(" ", 1)[1]
        out.append("Найбільше постраждалих " + " та ".join(hit) + ".")
    return out


def _major(seg):
    f = seg.get("score_breakdown") or {}
    return f.get("impact", 0) >= 0.9 and (seg.get("coverage") or 0) >= 8


def build_digest(items, by_id, evidence, date, max_details=3, max_region_killed=None):
    """items: the edition's stories (dicts with ids, title, lines, sources, rank, retold), in order.
    Returns (items with the strike stories replaced by one digest, digest log or None)."""
    strike = [it for it in items if any(is_strike_story(by_id[i], evidence) for i in it["ids"] if i in by_id)]
    # A strike that disrupted life for very many people (bridges of Kyiv) is its own story, not a line of the
    # summary; reports from occupied Crimea are about something else (owner, 2026-11-17).
    major = [it for it in strike if any(_major(by_id[i]) for i in it["ids"] if i in by_id)]
    strike = [it for it in strike if it not in major
              and not all((by_id[i].get("regions") or [None])[0] == "crimea" for i in it["ids"] if i in by_id)]
    if len(strike) < 2:
        return items, None
    segs = [by_id[i] for it in strike for i in it["ids"] if i in by_id]
    # A very large figure is usually a major attack — or the final toll of an earlier one (17.11.2026:
    # Komyshuvakha's 72 after the search ended). Its story stays on its own, before the summary, and its
    # figure is not part of the sum «за добу»; the other strike stories are still summed (owner, 17.11.2026).
    limit = max_region_killed if max_region_killed is not None else \
        config("editorial.json").get("daily", {}).get("strikes_max_region_killed", 20)
    result, skipped = tally(segs, evidence, date, max_killed=limit)
    big = set(result["big"])
    apart = major + [it for it in strike if any(src["item_id"] in big for src in it["sources"])]
    strike = [it for it in strike if it not in apart]
    if len(strike) < 2:
        return items, {"merged": False, "why": "менше двох сюжетів про удари без великої цифри", "skipped": skipped}
    segs = [by_id[i] for it in strike for i in it["ids"] if i in by_id]
    result, skipped2 = tally(segs, evidence, date, max_killed=limit)
    skipped = skipped + [x for x in skipped2 if x not in skipped]
    lead = lead_sentences(result, besides=bool(apart))
    if not lead:
        return items, {"merged": False, "why": "немає перевіреної цифри", "skipped": skipped}
    details = [it["lines"][0] for it in strike[:max_details] if it["lines"]]
    digest = {
        "ids": [i for it in strike for i in it["ids"]],
        "title": "Наслідки російських ударів",
        "lines": lead + details,
        "sources": [src for it in strike for src in it["sources"]],
        # after the stories set apart, so «Крім того» follows them
        "rank": max([min(it["rank"] for it in strike)] + [it["rank"] + 0.5 for it in apart]),
        "retold": any(it["retold"] for it in strike),
        "digest": {"killed": result["killed"], "injured": result["injured"], "regions": result["regions"],
                   "method": "у кожній області — найбільша цифра, підтверджена двома джерелами, а якщо такої немає "
                             "і джерела розходяться — найменша; області додано; загиблі й поранені окремо; за добу",
                   "apart": [i for it in apart for i in it["ids"]], "skipped": skipped},
    }
    rest = [it for it in items if it not in strike]
    out = sorted(rest + [digest], key=lambda it: it["rank"])
    return out, {"merged": True, "stories": len(strike), "killed": result["killed"], "injured": result["injured"],
                 "apart": [i for it in apart for i in it["ids"]]}


FINE = re.compile(r"[.;:!?\n]|,|\s+—\s+|\s+-\s+|\s+та\s+|\s+і\s+|\s+й\s+|\s+а також\s+")


def _figures(text):
    out = {}
    for c in (p.strip() for p in FINE.split(_norm(text))):
        f = c and clause_figure(c)
        if f and f[1] > out.get(f[0], 0):
            out[f[0]] = f[1]
    return out


def _names(text):
    return {w[:6].lower() for w in re.findall(r"\b[А-ЯІЇЄҐ][а-яіїєґ'’ʼ-]{3,}", _norm(text))}


def same_event(line, head, gaz):
    """Conservative: the headline names the same region, or shares a place or name with the line."""
    a, b = detect_places(line, gaz), detect_places(head, gaz)
    if a and b:
        return a == b
    return bool(_names(line) & _names(head))


def freshen(items):
    """A story's first paragraph is sometimes older than its own headline (17.11.2026: «наразі відомо
    про 31 загиблого» under the headline «кількість загиблих зросла до 72»). A sentence whose count of
    dead or injured is lower than one in a headline of the same story is replaced by that headline —
    the source's own words, so nothing is invented. Returns a log of replacements."""
    log, gaz = [], gazetteer()
    for it in items:
        heads = []
        for src in it.get("sources", []):
            t = (src.get("title") or "").strip()
            if t:
                heads.append((t, _figures(t)))
        if not heads:
            continue
        lines = []
        for line in it["lines"]:
            figs = _figures(line)
            for kind, value in figs.items():
                fresher = [(h, f[kind]) for h, f in heads if f.get(kind, 0) > value and same_event(line, h, gaz)]
                if fresher:
                    head = max(fresher, key=lambda x: x[1])[0]
                    head = re.sub(r"\s+-\s+", " — ", head).rstrip(" .") + "."
                    log.append({"story": it["ids"], "old": line, "new": head})
                    line = None if head in lines or head in it["lines"] else head
                    break
            if line:
                lines.append(line)
        it["lines"] = lines
    return log
