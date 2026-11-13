"""Homepage must feature only the existing BRIEF demo player."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_one_featured_player_no_extra_banner():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert html.count('id="demoCard"') == 1
    assert html.count('id="demoPlayer"') == 1
    assert 'id="latest-brief"' not in html
    assert 'id="home" class="screen active">\\n' not in html


def test_one_featured_edition_with_its_audio():
    """The player holds one edition: the 29 October demo until the first daily edition replaces it."""
    index = json.loads((ROOT / "demo" / "index.json").read_text(encoding="utf-8"))
    assert len(index["demos"]) == 1
    item = index["demos"][0]
    demo = json.loads((ROOT / item["file"]).read_text(encoding="utf-8"))
    assert demo["date"] == item["date"] >= "2026-10-29"
    assert (ROOT / demo["audio"]).is_file()


def test_old_standalone_url_uses_same_player():
    html = (ROOT / "brief-2026-10-29.html").read_text(encoding="utf-8")
    assert 'url=/demo.html' in html
    assert "<audio" not in html


def test_one_press_plays_the_whole_edition():
    """No paging through stories: one button, one progress bar for the whole edition (owner, 2026-11-13)."""
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    card = html[html.index('id="demoCard"'):html.index('<!-- daily automatic edition')]
    assert "Наступний" not in card and "Попередній" not in card
    assert 'id="demoPlay"' in card and 'id="demoBar"' in card
    assert "controls" not in card  # the browser's own per-file bar would show one story at a time
    assert "brief-prefs-saved" in html[html.index("function editionList"):]  # editorial order = the full mp3


def test_no_overpromise_on_length():
    for name in ("index.html", "demo.html"):
        html = (ROOT / name).read_text(encoding="utf-8")
        assert "за 5 хвилин" not in html.lower()
