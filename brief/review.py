"""Stage 7: editorial review and approval gate.

The editor edits editions/<date>/draft.json (directly or via review.html), may
exclude stories, rewrite sentences and confirm sensitive ones. `check_draft`
re-runs every check on the edited text against the stored evidence; `approve`
refuses to approve while any problem remains, and records who approved which
exact text (sha256). Rendering and publishing accept only that exact text.
"""
from .edition import EDITIONS, script_hash, script_text
from .factcheck import check_sentence
from .speech import load_lexicon, speech_text, speech_warnings
from .util import config, iso, load_json, now_utc, write_json



def load_draft(date):
    d = load_json(EDITIONS / date / "draft.json")
    if d is None:
        raise FileNotFoundError(f"no draft for {date}")
    return d


def _recheck_sentence(s, seg, evidence, ed, lexicon, year):
    """Re-verify one sentence after possible editing. Mutates and returns it."""
    s["speech_text"] = speech_text(s["text"], lexicon)
    s["speech_warnings"] = speech_warnings(s["speech_text"])
    if s["kind"] == "fact":
        attr = s.get("attribution_text") or ""
        at_end = s.get("attribution_position") == "end"
        present = s["text"].endswith(attr) if at_end else s["text"].startswith(attr)
        if attr and present:
            body = s["text"][: -len(attr)] if at_end else s["text"][len(attr):]
        else:
            body = s["text"]
            if attr:
                s["attribution"] = None  # editor removed/changed the attribution; claims still need sources
        story_ev = {src["item_id"]: evidence[src["item_id"]] for src in seg["sources"] if src["item_id"] in evidence}
        trace = check_sentence(body, story_ev, seg.get("independent_sources", 1), ed["sensitive"], year)
        s["body"] = body
        s.update(trace)
    elif s["kind"] == "coverage":
        from .edition import spoken_name

        names = {src["name"] for src in seg["sources"]} | {spoken_name(src["name"], ed["templates"])
                                                             for src in seg["sources"]}
        listed = [n.split(" та ще ")[0].strip(" .") for n in s["text"].split(":", 1)[-1].split(",")]
        unknown = [n for n in listed if n and n not in names]
        s["status"] = "unsupported" if unknown else "verified"
        s["reasons"] = [f"видання не серед джерел сюжету: {', '.join(unknown)}"] if unknown else []
    elif s["kind"] in ("template", "editorial"):
        if s.get("original_text") and s["text"] != s["original_text"]:
            s["kind"] = "editorial"
        if s["kind"] == "editorial":
            from .factcheck import extract_claims

            claims = [c for c in extract_claims(s["text"]) if c["type"] in ("number", "name", "quote")]
            s["status"] = "needs_review" if claims else "verified"
            s["reasons"] = ["редакційний текст із фактичними елементами — потребує підтвердження"] if claims else []
    return s


def check_draft(date, draft=None, save=True):
    draft = draft or load_draft(date)
    ed = config("editorial.json")
    lexicon = load_lexicon()
    year = int(date[:4])
    evidence = draft.get("evidence", {})
    problems = []
    included = 0
    for seg in draft["segments"]:
        if seg["kind"] == "story" and not seg.get("include", True):
            if seg.get("must_include"):
                problems.append(f"{seg['id']}: обов'язковий сюжет виключено — потрібне рішення редактора (must_include=false)")
            continue
        if seg["kind"] == "story":
            included += 1
        for s in seg["sentences"]:
            _recheck_sentence(s, seg, evidence, ed, lexicon, year)
            if not s["text"].strip():
                problems.append(f"{s['id']}: порожнє речення")
            if s.get("spoken_rewrite") and not (s.get("editor_confirmed") and s.get("confirmed_by") not in (None, "auto")):
                problems.append(f"{s['id']}: ШІ-переписування потребує підтвердження редактора")
            if s["status"] == "unsupported":
                problems.append(f"{s['id']}: непідтверджено — " + "; ".join(s.get("reasons", [])))
            elif s["status"] == "needs_review" and not s.get("editor_confirmed"):
                problems.append(f"{s['id']}: потребує підтвердження редактора — " + "; ".join(s.get("reasons", [])))
    intro = " ".join(s["text"] for seg in draft["segments"] if seg["kind"] in ("intro", "outro") for s in seg["sentences"])
    for phrase in ed["edition"].get("required_disclosure", ["сайті BRIEF"]):
        if phrase not in intro:
            problems.append(f"у вступі/завершенні бракує обов'язкового повідомлення: «{phrase}»")
    if not any(seg["kind"] == "story" and seg["block"] == "national" and seg.get("include", True)
               for seg in draft["segments"]):
        problems.append("немає жодного сюжету в блоці «Новини України»")
    sentences = [s for seg in draft["segments"] if seg["kind"] != "story" or seg.get("include", True)
                 for s in seg["sentences"]]
    draft["script_sha256"] = script_hash(draft)
    draft["last_checked_at"] = iso(now_utc())
    summary = {
        "date": date,
        "stories_included": included,
        "sentences": len(sentences),
        "verified": sum(1 for s in sentences if s["status"] == "verified"),
        "needs_review": sum(1 for s in sentences if s["status"] == "needs_review"),
        "confirmed_by_editor": sum(1 for s in sentences if s["status"] == "needs_review" and s.get("editor_confirmed")),
        "unsupported": sum(1 for s in sentences if s["status"] == "unsupported"),
        "script_sha256": draft["script_sha256"],
    }
    if save:
        write_json(EDITIONS / date / "draft.json", draft)
    return {"summary": summary, "problems": problems, "draft": draft}


class ApprovalError(RuntimeError):
    pass


AUTO_REVIEWER = "BRIEF auto (без редактора)"


def approve(date, reviewer, expected_hash=None, now=None, auto=False):
    """Record approval. auto=True: no human reviewer; ⚠ sentences are confirmed automatically
    (marked confirmed_by="auto"), ✗ sentences still block approval."""
    if auto:
        reviewer = AUTO_REVIEWER
    if not reviewer or not reviewer.strip():
        raise ApprovalError("reviewer is required")
    if auto and any(s.get("spoken_rewrite") for seg in load_draft(date)["segments"]
                    for s in seg["sentences"]):
        raise ApprovalError("AI-rewritten stories cannot be auto-approved")
    if auto:
        # Owner's decision (2026-10-21): sensitive claims (casualties, strikes) from a single
        # outlet are published without a human check. Claims missing from the sources (✗)
        # still block publication. Auto-confirmed sentences are marked in the record.
        draft = load_draft(date)
        for seg in draft["segments"]:
            for s in seg["sentences"]:
                if s.get("status") == "needs_review" and not s.get("editor_confirmed"):
                    s["editor_confirmed"] = True
                    s["confirmed_by"] = "auto"
        write_json(EDITIONS / date / "draft.json", draft)
    result = check_draft(date)
    if result["problems"]:
        raise ApprovalError("draft has unresolved problems:\n- " + "\n- ".join(result["problems"]))
    draft = result["draft"]
    digest = draft["script_sha256"]
    if expected_hash and not digest.startswith(expected_hash.strip().lower()):
        raise ApprovalError(f"script changed since review: expected {expected_hash}, got {digest}")
    segments = [seg for seg in draft["segments"] if seg["kind"] != "story" or seg.get("include", True)]
    approved = {
        "date": date,
        "status": "approved",
        "approved_by": reviewer.strip(),
        "mode": "auto" if auto else "editor",
        "approved_at": iso(now or now_utc()),
        "script_sha256": digest,
        "script_text": script_text(draft),
        "segments": segments,
        "evidence": draft["evidence"],
        "checks": result["summary"],
    }
    write_json(EDITIONS / date / "approved.json", approved)
    draft["status"] = "approved"
    write_json(EDITIONS / date / "draft.json", draft)
    return approved


def load_approved(date):
    a = load_json(EDITIONS / date / "approved.json")
    if a is None:
        raise ApprovalError(f"edition {date} is not approved")
    recomputed = script_hash({"segments": a["segments"]})
    if recomputed != a["script_sha256"]:
        raise ApprovalError("approved.json was modified after approval (sha256 mismatch)")
    return a
