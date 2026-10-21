import re

_SENT_END = re.compile(r"(?<=[.!?…»])\s+")
_SOFT = re.compile(r"(?<=[,;:—–])\s+")


def _norm(s):
    return re.sub(r"\s+", " ", s).strip()


def _split_long(text, limit):
    """Split an over-long sentence at clause boundaries, then at spaces."""
    parts, cur = [], ""
    for piece in _SOFT.split(text):
        cand = f"{cur} {piece}".strip() if cur else piece
        if len(cand) <= limit:
            cur = cand
            continue
        if cur:
            parts.append(cur)
        while len(piece) > limit:
            cut = piece.rfind(" ", 0, limit)
            cut = cut if cut > 0 else limit
            parts.append(piece[:cut].strip())
            piece = piece[cut:].strip()
        cur = piece
    if cur:
        parts.append(cur)
    return parts


def chunk_text(text, limit, measure=len):
    """Split text into chunks of at most `limit` (by `measure`) at sentence boundaries.

    Guarantees: order preserved, nothing dropped or duplicated (asserted).
    """
    sentences = [s for s in _SENT_END.split(text.strip()) if s]
    chunks, cur = [], ""
    for s in sentences:
        pieces = [s] if measure(s) <= limit else _split_long(s, limit)
        for p in pieces:
            cand = f"{cur} {p}" if cur else p
            if measure(cand) <= limit:
                cur = cand
            else:
                if cur:
                    chunks.append(cur)
                cur = p
    if cur:
        chunks.append(cur)
    if _norm(" ".join(chunks)) != _norm(text):
        raise AssertionError("chunking changed the text")
    if any(measure(c) > limit for c in chunks):
        raise AssertionError("chunk over limit")
    return chunks
