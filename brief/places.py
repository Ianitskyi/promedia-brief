"""Stress of village and town names, checked against Ukrainian Wikipedia (owner, 2026-11-17).

The voice read «Са́дове» for the village Садо́ве near Kherson. The general stress dictionary does not know
small places, so before voicing: every settlement named in the edition's sources («села Садове») is looked
up in Ukrainian Wikipedia, whose articles mark the stress in the first line («Садо́ве — село в Україні…»).
Only an article about a place in the story's region counts, and only if all such articles agree. Found
stresses are kept in data/place-stress.json (with the article as the source) and used like
config/stress.json; names that could not be checked are listed in the edition's log for the editor.
"""
import json
import re
import urllib.parse

from .http import FetchError, fetch
from .util import ROOT, load_json, write_json

STORE = ROOT / "data" / "place-stress.json"
STRESS = "́"
API = "https://uk.wikipedia.org/w/api.php?"
VOWELS = "аеєиіїоуюяАЕЄИІЇОУЮЯ"
SETTLEMENT = re.compile(r"(?<![\w'’])(?:сел[оаіу]|селищ[еаіу]|міст[оаі]|смт|с\.)\s+"
                        r"([А-ЯІЇЄҐ][а-яіїєґ'’]+(?:-[А-ЯІЇЄҐа-яіїєґ'’]+)?)")
# region id -> the adjective stem of its oblast as Wikipedia writes it («Херсонської області»)
OBLAST = {"vinnytsia": "Вінницьк", "volyn": "Волинськ", "dnipropetrovsk": "Дніпропетровськ", "donetsk": "Донецьк",
          "zhytomyr": "Житомирськ", "zakarpattia": "Закарпатськ", "zaporizhzhia": "Запорізьк",
          "ivano-frankivsk": "Івано-Франківськ", "kyiv": "Київськ", "kirovohrad": "Кіровоградськ",
          "luhansk": "Луганськ", "lviv": "Львівськ", "mykolaiv": "Миколаївськ", "odesa": "Одеськ",
          "poltava": "Полтавськ", "rivne": "Рівненськ", "sumy": "Сумськ", "ternopil": "Тернопільськ",
          "kharkiv": "Харківськ", "kherson": "Херсонськ", "khmelnytskyi": "Хмельницьк", "cherkasy": "Черкаськ",
          "chernivtsi": "Чернівецьк", "chernihiv": "Чернігівськ", "crimea": "Крим"}


def settlements(text):
    """Settlement names in the nominative, as sources write them after «село», «селище», «місто»."""
    # a short word («Біла» of «Біла Церква») would mark too many other words; such names stay unchecked
    return sorted({m.group(1) for m in SETTLEMENT.finditer(text or "") if len(m.group(1)) >= 5})


def _api(params, get=fetch):
    raw = get(API + urllib.parse.urlencode({**params, "format": "json", "formatversion": "2"}), timeout=20, retries=2)
    return json.loads(raw)


def lookup(name, region, get=fetch):
    """(stressed name, article URL) from Ukrainian Wikipedia, or (None, reason)."""
    oblast = OBLAST.get(region)
    if not oblast:
        return None, "невідома область"
    try:
        found = _api({"action": "query", "list": "search", "srsearch": f'"{name}" {oblast}', "srlimit": 8,
                      "srnamespace": 0}, get)
        titles = [h["title"] for h in found["query"]["search"] if h["title"].split(" (")[0] == name]
        if not titles:
            return None, "статті не знайдено"
        pages = _api({"action": "query", "prop": "extracts", "exintro": 1, "explaintext": 1, "exsentences": 2,
                      "titles": "|".join(titles[:8])}, get)["query"]["pages"]
    except (FetchError, KeyError, ValueError) as e:
        return None, f"помилка запиту: {e}"
    forms = {}
    for p in pages:
        extract = p.get("extract") or ""
        if oblast not in extract:
            continue
        for w in re.findall(r"[\w'’́-]+", extract.split("—")[0]):
            if STRESS in w and w.replace(STRESS, "") == name.split()[0]:
                forms.setdefault(w, p["title"])
    if len(forms) != 1:
        return None, "наголос не вказано" if not forms else "статті розходяться: " + ", ".join(forms)
    stressed, title = next(iter(forms.items()))
    return stressed, "https://uk.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


def entry(stressed):
    """A config/stress.json-style entry that also covers the case forms (Садове, Садового, Садовому)."""
    plain = stressed.replace(STRESS, "")
    pos = stressed.index(STRESS)  # the stressed vowel is plain[pos - 1]
    stem = plain[:-1] if plain[-1] in VOWELS and pos < len(plain) else plain
    if pos > len(stem):  # stress on the ending: the bare name only
        return {"word": plain, "stressed": plain[:pos] + "+" + plain[pos:], "prefix": False}
    return {"word": stem, "stressed": stem[:pos] + "+" + stem[pos:], "prefix": True}


def check(spoken, approved, get=fetch):
    """Look up every settlement named in the sources of the edition's stories. Returns the log."""
    store = load_json(STORE, {"note": __doc__.strip().splitlines()[0], "places": {}})
    log = {"checked": [], "unchecked": []}
    region_of = {s["id"]: s.get("regions") or [] for s in approved.get("segments", [])}
    for seg in spoken.get("segments", []):
        regions = next((region_of[i] for i in seg.get("from_stories") or [] if region_of.get(i)), [])
        text = " ".join(approved.get("evidence", {}).get(src["item_id"], "") for src in seg.get("sources", []))
        text += " " + " ".join(s["text"] for s in seg.get("sentences", []))
        for name in settlements(text):
            key = f"{name}|{regions[0] if regions else ''}"
            if key in store["places"]:
                continue
            said = " ".join(s["text"] for s in seg.get("sentences", []))
            if name[:max(3, len(name) - 2)] not in said:  # only places the listener will hear
                continue
            stressed, source = lookup(name, regions[0], get) if regions else (None, "регіон сюжету невідомий")
            if stressed:
                store["places"][key] = {"wiki": stressed, "source": source, **entry(stressed)}
                log["checked"].append({"name": name, "stressed": stressed, "source": source})
            else:
                log["unchecked"].append({"name": name, "why": source})
    write_json(STORE, store)
    return log


def stress_entries():
    store = load_json(STORE, {"places": {}})
    return [{"word": p["word"], "stressed": p["stressed"], "prefix": p["prefix"]} for p in store["places"].values()]
