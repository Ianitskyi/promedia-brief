"""Text, URL and date normalisation shared by all pipeline stages."""
import datetime as dt
import email.utils
import hashlib
import html
import re
import urllib.parse

TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|yclid$|mc_|ref$|from$|_ga$)")

# Phrases that RSS feeds append to annotations; they are not part of the news.
TRAILERS = re.compile(
    r"\s*(Читати далі|Читайте також|Детальніше|Повний текст|Read more|Докладніше)\b.*$",
    re.I | re.S,
)


def canonical_url(url: str) -> str:
    url = (url or "").strip()
    p = urllib.parse.urlsplit(url)
    host = p.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    query = [
        (k, v)
        for k, v in urllib.parse.parse_qsl(p.query, keep_blank_values=True)
        if not TRACKING_PARAMS.match(k.lower())
    ]
    path = p.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    return urllib.parse.urlunsplit(("https", host.lower(), path, urllib.parse.urlencode(query), ""))


def url_host(url: str) -> str:
    host = urllib.parse.urlsplit(url or "").hostname or ""
    return host[4:] if host.startswith("www.") else host


def host_matches(url: str, domains) -> bool:
    host = url_host(url)
    return any(host == d or host.endswith("." + d) for d in domains)


def item_id(url: str) -> str:
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:16]


def parse_date(value):
    """Parse RSS/Atom/ISO dates into an aware UTC datetime. Returns None if unknown."""
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        d = value
    else:
        s = str(value).strip()
        if not s:
            return None
        d = None
        try:
            d = email.utils.parsedate_to_datetime(s)
        except (TypeError, ValueError, IndexError):
            d = None
        if d is None:
            try:
                d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            except ValueError:
                return None
    if d.tzinfo is None:
        # A date without zone from a Ukrainian newsroom is Kyiv local time.
        from .util import KYIV

        d = d.replace(tzinfo=KYIV)
    return d.astimezone(dt.timezone.utc)


def clean_text(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"<(script|style)\b.*?</\1>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<br\s*/?>|</p>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = s.replace(" ", " ").replace("​", "")
    s = re.sub(r"\s+", " ", s).strip()
    # Feeds that strip block tags glue sentences: "в соцмережі X.Віцепрезидентка",
    # "пропозиціямиЗустріч". Restore the missing space.
    s = re.sub(r"([A-Za-zА-ЯІЇЄҐа-яіїєґ][.!?…])([А-ЯІЇЄҐ])", r"\1 \2", s)
    s = re.sub(r"([.!?…])([\"«„“])([А-ЯІЇЄҐ])", r"\1 \2\3", s)
    s = re.sub(r"([а-яіїєґ])([А-ЯІЇЄҐ][а-яіїєґ'’]{2,})", r"\1 \2", s)
    # Drupal bylines at the start of annotations: "Ім'я Прізвище вт, 20/10/2026 - 17:47 Текст"
    s = re.sub(r"^[^.]{0,60}?\b(?:пн|вт|ср|чт|пт|сб|нд), \d{2}/\d{2}/\d{4} - \d{2}:\d{2}\s+", "", s)
    s = TRAILERS.sub("", s).strip()
    return s


ABBREV = r"(?:м|вул|просп|обл|р|рр|ст|тис|млн|млрд|грн|дол|див|с|смт|пл|ім|т\.\s?зв|та ін|і т\.\s?д)"
_SENT = re.compile(r"([.!?…][\"»”]?)\s+(?=[\"«„“(—–-]?\s?[А-ЯІЇЄҐA-Z0-9])")


def split_sentences(text: str):
    text = clean_text(text)
    if not text:
        return []
    out, start = [], 0
    for m in _SENT.finditer(text):
        before = text[start:m.end(1)]
        # Do not split after common abbreviations ("м. Київ", "15 тис. гривень").
        if re.search(r"(?:^|\s)" + ABBREV + r"\.$", before, flags=re.I):
            continue
        if re.search(r"(?:^|\s)[А-ЯІЇЄҐA-Z]\.$", before):  # initials: "В. Зеленський"
            continue
        out.append(before.strip())
        start = m.end()
    out.append(text[start:].strip())
    return [s for s in out if s]


WORD = re.compile(r"[A-Za-zА-ЯІЇЄҐа-яіїєґ'’ʼ\-]+|\d+(?:[.,]\d+)?")

STOPWORDS = set(
    """і й та а але або що як це цей ця ці той та те ті у в на з із зі до від по за про під над при для через
    після перед між без його її їх він вона вони воно ми ви ти я не ні так також ще вже лише тільки може
    було буде були був була є бути має мають які який яка яке де коли щоб чи бо же ж ось там тут
    понад близько майже року році роки році днів день дня години заявив заявила повідомив повідомила
    повідомили сказав каже кажуть розповів розповіла новини новина сьогодні вчора""".split()
)


def norm_word(w: str) -> str:
    return w.lower().replace("’", "'").replace("ʼ", "'")


def stem(w: str) -> str:
    """Crude Ukrainian stemmer: fixed-length prefix, so case endings do not matter.

    «Епіцентр» / «Епіцентру» -> «епіцен»; «атака» / «атаки» -> «атак».
    """
    w = norm_word(w)
    if w.isdigit() or len(w) <= 4:
        return w
    if len(w) <= 7:
        return w[: min(6, len(w) - 1)]
    return w[:6]


def tokens(text: str):
    return [norm_word(t) for t in WORD.findall(text or "")]


def content_stems(text: str):
    return [stem(t) for t in tokens(text) if t not in STOPWORDS and (len(t) > 2 or t.isdigit())]


NUM = re.compile(r"(?<![\w.,])\d{1,3}(?:[  ]\d{3})+(?:[.,]\d+)?(?!\w)|(?<![\w.,])\d+(?:[.,]\d+)?(?!\w)")


def numbers(text: str):
    """Numbers as canonical strings: '1 200' -> '1200', '2,5' -> '2.5'."""
    out = []
    for m in NUM.finditer(text or ""):
        n = re.sub(r"[  ]", "", m.group(0)).replace(",", ".")
        out.append(n)
    return out
