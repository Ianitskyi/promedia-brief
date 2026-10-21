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


def cardinal(n: int) -> str:
    """Nominative cardinal. Agreement with the noun is left to the lexicon/editor."""
    if n == 0:
        return "нуль"
    parts, scale = [], 0
    while n:
        n, triad = divmod(n, 1000)
        if triad:
            words = _triad(triad, feminine=(scale == 1))
            if scale:
                words.append(_plural(triad, SCALES[scale]))
            parts.insert(0, " ".join(words))
        scale += 1
    return " ".join(parts)


def spell_numbers(text):
    def repl(m):
        raw = re.sub(r"[  ]", "", m.group(0))
        if "," in raw or "." in raw:
            whole, frac = re.split(r"[.,]", raw, 1)
            return f"{cardinal(int(whole))} кома {cardinal(int(frac))}"
        return cardinal(int(raw))

    return re.sub(r"\d{1,3}(?:[  ]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?", repl, text)


def load_lexicon():
    return config("lexicon.json")["entries"]


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


def speech_text(text, entries=None, spell_digits=False, lowercase=False, transliterate=False):
    out = apply_lexicon(text, entries if entries is not None else load_lexicon())
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
