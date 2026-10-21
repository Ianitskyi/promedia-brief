"""Stage 6: claim-level traceability for script sentences.

For every sentence we extract checkable claims and look for each one in the stored
evidence (title + annotation of the source publications):

    sentence -> claims (numbers, names, quotes, dates) -> item ids -> URLs

Statuses
  verified      every claim was found in the evidence (and the sentence is not sensitive,
                or the event is confirmed by >= 2 independent outlets)
  needs_review  claims found, but the sentence reports casualties/combat/etc. from a single
                outlet; an editor must explicitly confirm it
  unsupported   at least one claim was not found in the evidence; cannot be approved

This is an automated aid, not a guarantee: it catches invented numbers, names and
quotes, but it cannot judge whether a paraphrase changed the meaning. Editors approve.
"""
import re

from .classify import is_sensitive
from .normalize import WORD, norm_word, numbers, stem

MONTHS = ["січ", "лют", "берез", "квіт", "трав", "черв", "лип", "серп", "верес", "жовт", "листопад", "груд"]
WEEKDAYS = ["понеділ", "вівтор", "серед", "четвер", "п'ятниц", "субот", "неділ"]
QUOTE = re.compile(r"«([^»]{3,})»|“([^”]{3,})”|\"([^\"]{3,})\"")
IGNORED_NAMES = {"brief"}


def _norm_space(s):
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("ʼ", "'")).strip().lower()


def name_claims(text):
    """Capitalised words that are not sentence-initial: names, places, organisations."""
    out = []
    prev_end_punct = True
    for m in WORD.finditer(text):
        w = m.group(0)
        if w[:1].isupper() and not prev_end_punct and norm_word(w) not in IGNORED_NAMES and len(w) > 1:
            out.append(w)
        after = text[m.end():m.end() + 3]
        prev_end_punct = re.match(r"\s*[.!?:«\"“(]", after) is not None
    return out


def extract_claims(text):
    claims = []
    for n in numbers(text):
        claims.append({"type": "number", "value": n})
    for q in QUOTE.findall(text):
        q = next(x for x in q if x)
        claims.append({"type": "quote", "value": q})
    for w in name_claims(text):
        claims.append({"type": "name", "value": w})
    low = text.lower()
    for m in MONTHS + WEEKDAYS:
        if re.search(r"(?<![\w'])" + m, low):
            claims.append({"type": "date", "value": m})
    seen, out = set(), []
    for c in claims:
        k = (c["type"], c["value"].lower())
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def _found(claim, evidence_text):
    t, v = claim["type"], claim["value"]
    if t == "number":
        return v in numbers(evidence_text)
    if t == "quote":
        return _norm_space(v) in _norm_space(evidence_text)
    if t == "name":
        target = stem(v)
        ev = {stem(w) for w in WORD.findall(evidence_text)}
        if target in ev:
            return True
        # tolerate case endings: compare a shorter common prefix for long names
        p = norm_word(v)[: max(4, len(v) - 3)]
        return any(norm_word(w).startswith(p) for w in WORD.findall(evidence_text))
    if t == "date":
        return bool(re.search(r"(?<![\w'])" + v, evidence_text.lower()))
    return False


def check_sentence(body, evidence, independent_sources, sensitive_cfg, current_year=None):
    """`body` is the factual part of the sentence (attribution removed).

    `evidence` maps item_id -> text. Returns the claim trace and a status.
    """
    claims = extract_claims(body)
    for c in claims:
        c["found_in"] = [iid for iid, txt in evidence.items() if _found(c, txt)]
    missing = [c for c in claims if not c["found_in"]]
    sensitive = is_sensitive(body, sensitive_cfg)
    old_years = [y for y in re.findall(r"(?<!\d)(19\d\d|20\d\d)(?!\d)", body) if current_year and int(y) < current_year]
    if missing:
        status = "unsupported"
    elif (sensitive and independent_sources < 2) or old_years:
        status = "needs_review"
    else:
        status = "verified"
    reasons = [f"не знайдено в джерелах: {c['type']} «{c['value']}»" for c in missing]
    if old_years:
        reasons.append("згадано минулі роки (" + ", ".join(old_years) + ") — перевірте, чи це нова подія")
    if sensitive and status != "unsupported":
        reasons.append("чутлива тема (" + ", ".join(sensitive[:3]) + f"); незалежних джерел: {independent_sources}")
    return {"claims": claims, "status": status, "sensitive": sensitive, "reasons": reasons}
