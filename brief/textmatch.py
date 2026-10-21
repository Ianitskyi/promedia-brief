import functools
import re


@functools.lru_cache(maxsize=4096)
def _marker_re(marker: str):
    m = re.escape(marker.lower()).replace(r"\ ", r"\s+")
    # Short markers (abbreviations) must match a whole word; longer ones are word-start prefixes.
    tail = r"(?![\w'’])" if len(marker) <= 3 else ""
    return re.compile(r"(?<![\w'’])" + m + tail)


def has_marker(text: str, marker: str) -> bool:
    return bool(_marker_re(marker).search(text.lower()))


def count_markers(text: str, markers) -> int:
    low = text.lower()
    return sum(1 for m in markers if _marker_re(m).search(low))
