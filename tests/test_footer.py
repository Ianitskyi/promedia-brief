"""BRIEF pages carry the standard ProMedia footer, like the other subdomains."""
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("page", ["index.html", "demo.html"])
def test_standard_promedia_footer(page):
    html = (ROOT / page).read_text(encoding="utf-8")
    # The shared shell renders <promedia-global-footer>, but only adds the header by itself.
    assert html.count("<promedia-global-footer></promedia-global-footer>") == 1
    assert html.index("</main>") < html.index("<promedia-global-footer>")
    assert "news.promedia.report/js/promedia-global-shell.js" in html
