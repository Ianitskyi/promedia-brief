"""Speech layer: turns approved display text into text for TTS.

Only pronunciation changes are allowed here (lexicon entries, number reading for
engines that cannot read digits). Editors approve the display text; the speech
text is derived from it deterministically and stored next to it for review.
"""
import re

from .util import config

MONTHS_GEN = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня", "серпня", "вересня",
              "жовтня", "листопада", "грудня"]
ORD_NEUT = {1: "перше", 2: "друге", 3: "третє", 4: "четверте", 5: "п'яте", 6: "шосте", 7: "сьоме", 8: "восьме",
            9: "дев'яте", 10: "десяте", 11: "одинадцяте", 12: "дванадцяте", 13: "тринадцяте", 14: "чотирнадцяте",
            15: "п'ятнадцяте", 16: "шістнадцяте", 17: "сімнадцяте", 18: "вісімнадцяте", 19: "дев'ятнадцяте",
            20: "двадцяте", 30: "тридцяте"}


def date_words(iso_date):
    """'2026-10-20' -> 'двадцяте жовтня' (form used after «за»: «випуск за двадцяте жовтня»)."""
    y, m, d = (int(x) for x in iso_date.split("-"))
    if d in ORD_NEUT:
        day = ORD_NEUT[d]
    else:
        day = ("двадцять " if d < 30 else "тридцять ") + ORD_NEUT[d % 10]
    return f"{day} {MONTHS_GEN[m - 1]}"


ONES = ["нуль", "один", "два", "три", "чотири", "п'ять", "шість", "сім", "вісім", "дев'ять", "десять",
        "одинадцять", "дванадцять", "тринадцять", "чотирнадцять", "п'ятнадцять", "шістнадцять", "сімнадцять",
        "вісімнадцять", "дев'ятнадцять"]
TENS = ["", "", "двадцять", "тридцять", "сорок", "п'ятдесят", "шістдесят", "сімдесят", "вісімдесят", "дев'яносто"]
HUNDREDS = ["", "сто", "двісті", "триста", "чотириста", "п'ятсот", "шістсот", "сімсот", "вісімсот", "дев'ятсот"]
SCALES = [("", "", ""), ("тисяча", "тисячі", "тисяч"), ("мільйон", "мільйони", "мільйонів"),
          ("мільярд", "мільярди", "мільярдів")]


def _plural(n, forms):
    n = n % 100
    if 11 <= n <= 19:
        return forms[2]
    return forms[0] if n % 10 == 1 else forms[1] if 2 <= n % 10 <= 4 else forms[2]


def _triad(n, feminine=False):
    words = []
    if n >= 100:
        words.append(HUNDREDS[n // 100])
        n %= 100
    if n >= 20:
        words.append(TENS[n // 10])
        n %= 10
    if n or not words:
        if n == 0 and words:
            pass
        elif feminine and n in (1, 2):
            words.append("одна" if n == 1 else "дві")
        else:
            words.append(ONES[n])
    return [w for w in words if w]


def cardinal(n: int, feminine=False) -> str:
    """Nominative cardinal; feminine=True gives «одна/дві» for nouns like «гривня», «людина»."""
    if n == 0:
        return "нуль"
    parts, scale = [], 0
    while n:
        n, triad = divmod(n, 1000)
        if triad:
            words = _triad(triad, feminine=(scale == 1) or (scale == 0 and feminine))
            if scale:
                if not n and triad == 1:
                    words = []  # «тисяча двісті», not «одна тисяча двісті»
                words.append(_plural(triad, SCALES[scale]))
            parts.insert(0, " ".join(words))
        scale += 1
    return " ".join(parts)


ORD_STEMS = {1: "перш", 2: "друг", 3: "трет", 4: "четверт", 5: "п'ят", 6: "шост", 7: "сьом", 8: "восьм",
             9: "дев'ят", 10: "десят", 11: "одинадцят", 12: "дванадцят", 13: "тринадцят", 14: "чотирнадцят",
             15: "п'ятнадцят", 16: "шістнадцят", 17: "сімнадцят", 18: "вісімнадцят", 19: "дев'ятнадцят",
             20: "двадцят", 30: "тридцят", 40: "сороков", 50: "п'ятдесят", 60: "шістдесят", 70: "сімдесят",
             80: "вісімдесят", 90: "дев'яност", 100: "сот", 200: "двохсот", 300: "трьохсот", 400: "чотирьохсот",
             500: "п'ятисот", 600: "шестисот", 700: "семисот", 800: "восьмисот", 900: "дев'ятисот"}
ORD_ENDINGS = {"nom": "ий", "gen": "ого", "loc": "ому", "neut": "е", "plgen": "их"}
THIRD = {"nom": "третій", "gen": "третього", "loc": "третьому", "neut": "третє", "plgen": "третіх"}


def ordinal(n: int, case="nom") -> str:
    """Masculine ordinal: ordinal(2026, "gen") -> «дві тисячі двадцять шостого» (року)."""
    if n % 1000 == 0:
        head = {1000: "тисячн", 2000: "двотисячн", 3000: "тритисячн"}.get(n)
        return head + ORD_ENDINGS[case] if head else cardinal(n)
    rest = n % 100 if n % 100 else n % 1000
    if n % 100 >= 20 and n % 10:
        rest = n % 10
    elif n % 100 >= 20:
        rest = n % 100
    prefix = cardinal(n - rest) if n - rest else ""
    word = THIRD[case] if rest == 3 else ORD_STEMS[rest] + ORD_ENDINGS[case]
    return f"{prefix} {word}".strip()


# Nouns that change form after a number: (one, few, many, feminine, form after a fraction).
NOUNS = [
    ("гривня", "гривні", "гривень", True, "гривні"),
    ("тисяча", "тисячі", "тисяч", True, "тисячі"),
    ("мільйон", "мільйони", "мільйонів", False, "мільйона"),
    ("мільярд", "мільярди", "мільярдів", False, "мільярда"),
    ("відсоток", "відсотки", "відсотків", False, "відсотка"),
    ("кілометр", "кілометри", "кілометрів", False, "кілометра"),
    ("людина", "людини", "людей", True, "людини"),
    ("особа", "особи", "осіб", True, "особи"),
    ("дитина", "дитини", "дітей", True, "дитини"),
    ("година", "години", "годин", True, "години"),
    ("хвилина", "хвилини", "хвилин", True, "хвилини"),
    ("ракета", "ракети", "ракет", True, "ракети"),
    ("громада", "громади", "громад", True, "громади"),
    ("область", "області", "областей", True, "області"),
    ("країна", "країни", "країн", True, "країни"),
    ("сім'я", "сім'ї", "сімей", True, "сім'ї"),
    ("одиниця", "одиниці", "одиниць", True, "одиниці"),
]
_NOUN_BY_FORM = {f: n for n in NOUNS for f in n[:3]}
_MONTHS = "|".join(MONTHS_GEN)
_YEAR_CASE = {"рік": "nom", "року": "gen", "році": "loc", "роки": "nom", "років": "gen", "роках": "loc"}
_NUM = r"\d{1,3}(?:[  ]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?"


def _fraction(whole, frac, noun):
    if frac == "5":
        return f"{cardinal(whole, feminine=bool(noun and noun[3]))} з половиною", "whole"
    fem_whole = cardinal(whole, feminine=True)
    ciler = "ціла" if whole % 10 == 1 and whole % 100 != 11 else "цілих"
    f = int(frac)
    denom = {1: "десят", 2: "сот", 3: "тисячн"}.get(len(frac), "тисячн")
    tail = denom + ("а" if f % 10 == 1 and f % 100 != 11 else "их")
    return f"{fem_whole} {ciler} {cardinal(f, feminine=True)} {tail}", "fraction"


UNIT_COMB = {1: "одно", 2: "дво", 3: "три", 4: "чотири", 5: "п'яти", 6: "шести", 7: "семи", 8: "восьми", 9: "дев'яти"}
TEEN_COMB = {10: "десяти", 11: "одинадцяти", 12: "дванадцяти", 13: "тринадцяти", 14: "чотирнадцяти", 15: "п'ятнадцяти",
             16: "шістнадцяти", 17: "сімнадцяти", 18: "вісімнадцяти", 19: "дев'ятнадцяти"}
TENS_COMB = {2: "двадцяти", 3: "тридцяти", 4: "сорока", 5: "п'ятдесяти", 6: "шістдесяти", 7: "сімдесяти", 8: "вісімдесяти",
             9: "дев'яноста"}


def compound(n):
    """First part of a compound adjective: 43-річний -> «сорокатри» + «річний»."""
    if n == 100:
        return "сто"
    if n < 10:
        return UNIT_COMB.get(n)
    if n < 20:
        return TEEN_COMB[n]
    if n < 100:
        return TENS_COMB[n // 10] + (UNIT_COMB[n % 10] if n % 10 else "")
    return None


def spell_numbers(text):
    """Digits -> words with the grammar a listener expects:
    «21 жовтня» -> «двадцять першого жовтня», «2026 року» -> «дві тисячі двадцять шостого року»,
    «1 гривень» -> «одна гривня», «2,5 мільярдів» -> «два з половиною мільярди»."""
    text = re.sub(r"\b(\d{1,2})\s*[–—-]\s*(\d{1,2})\s+(" + _MONTHS + r")\b",
                  lambda m: f"{ordinal(int(m[1]), 'gen')} – {ordinal(int(m[2]), 'gen')} {m[3]}", text)
    text = re.sub(r"\b(\d{1,2})\s+(" + _MONTHS + r")\b", lambda m: f"{ordinal(int(m[1]), 'gen')} {m[2]}", text)
    text = re.sub(r"\b(\d+)-(го|му|й|ий|х)\b",
                  lambda m: ordinal(int(m[1]), {"го": "gen", "му": "loc", "х": "plgen"}.get(m[2], "nom")), text)
    text = re.sub(r"\b(\d{1,3})-(?!(?:го|му|й|ий|х)\b)([а-яіїєґ'’]{3,})",
                  lambda m: (compound(int(m[1])) + m[2]) if compound(int(m[1])) else m[0], text)
    text = re.sub(r"\b(\d{4})\s+(" + "|".join(_YEAR_CASE) + r")\b",
                  lambda m: f"{ordinal(int(m[1]), _YEAR_CASE[m[2]])} {m[2]}", text)

    def repl(m):
        raw, space, word = re.sub(r"[  ]", "", m[1]), m[2], m[3]
        noun = _NOUN_BY_FORM.get(word.lower()) if space else None
        if "," in raw or "." in raw:
            whole, frac = re.split(r"[.,]", raw, maxsplit=1)
            spoken, kind = _fraction(int(whole), frac.rstrip("0") or "0", noun)
            if noun:
                word = noun[4] if kind == "fraction" else _plural(int(whole), noun[:3])
        else:
            n = int(raw)
            spoken = cardinal(n, feminine=bool(noun and noun[3]))
            if noun:
                word = _plural(n, noun[:3])
            elif space and word.lower() in _FEM_ACC and n % 10 == 1 and n % 100 != 11:
                spoken = spoken[: -len("один")] + "одну"  # «поранили одну людину»
        return spoken + space + word

    return re.sub(r"(" + _NUM + r")(\s*)([\w'’]*)", repl, text)


_FEM_ACC = {n[0][:-1] + ("ю" if n[0].endswith("я") else "у") for n in NOUNS if n[3] and n[0][-1] in "ая"}


def load_lexicon():
    return config("lexicon.json")["entries"]


def load_stress():
    try:
        return config("stress.json")["entries"]
    except FileNotFoundError:
        return []


STRESS = "\u0301"  # combining acute accent, placed after the stressed vowel


def apply_stress(text, entries):
    """Mark stress in words the engine's own dictionary gets wrong (config/stress.json).
    Only for engines that read stress marks; the approved display text never changes."""
    for e in sorted(entries, key=lambda e: -len(e["word"])):
        tail = r"[\w'’]*" if e.get("prefix") else ""
        stressed = e["stressed"].replace("+", STRESS)
        text = re.sub(r"(?<![\w'’])" + re.escape(e["word"]) + r"(?=" + tail + r"(?![\w'’]))",
                      stressed, text)
    return text


def apply_lexicon(text, entries):
    for e in sorted(entries, key=lambda e: -len(e["written"])):
        w = re.escape(e["written"])
        flags = 0 if e.get("case_sensitive", True) else re.I
        before = r"(?<![\w'’])" if re.match(r"\w", e["written"]) else ""
        text = re.sub(before + w + r"(?![\w'’])", e["spoken"], text, flags=flags)
    return text


LATIN = {"a": "а", "b": "б", "c": "к", "d": "д", "e": "е", "f": "ф", "g": "г", "h": "г", "i": "і", "j": "дж",
         "k": "к", "l": "л", "m": "м", "n": "н", "o": "о", "p": "п", "q": "к", "r": "р", "s": "с", "t": "т", "u": "у",
         "v": "в", "w": "в", "x": "кс", "y": "і", "z": "з"}


def transliterate_latin(text):
    """Last-resort fallback for engines that skip Latin letters entirely (Piper).

    Rough, letter-by-letter; proper names belong in the lexicon. Only used when the
    engine would otherwise drop the word silently.
    """
    def word(m):
        w = m.group(0)
        out = "".join(LATIN.get(ch.lower(), ch) for ch in w)
        return out.upper() if w.isupper() and len(w) > 1 else out

    return re.sub(r"[A-Za-z]+", word, text)


def speech_text(text, entries=None, spell_digits=False, lowercase=False, transliterate=False, stress=None):
    out = apply_lexicon(text, entries if entries is not None else load_lexicon())
    if stress:
        out = apply_stress(out, stress)
    if spell_digits:
        out = spell_numbers(out)
    if transliterate:
        out = transliterate_latin(out)
    if lowercase:
        out = out.lower()
    return out


def speech_warnings(text):
    """Things TTS engines tend to misread; shown to the editor, never auto-fixed."""
    w = []
    if re.search(r"[$€£№§]", text):
        w.append("символ валюти/знак — перевірте, як буде прочитано")
    latin = sorted(set(re.findall(r"\b[A-Za-z][A-Za-z.]{1,}\b", text)))
    if latin:
        w.append("латиниця: " + ", ".join(latin[:5]) + " — додайте до словника вимови")
    if re.search(r"\d+[-–]\d+", text):
        w.append("діапазон чисел — перевірте читання")
    if re.search(r"\b[А-ЯІЇЄҐ]{2,}\b", text):
        abbr = sorted(set(re.findall(r"\b[А-ЯІЇЄҐ]{2,}\b", text)))
        w.append("абревіатури: " + ", ".join(abbr[:5]))
    return w
