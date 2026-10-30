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


def test_latest_demo_replaces_october_22():
    index = json.loads((ROOT / "demo" / "index.json").read_text(encoding="utf-8"))
    assert len(index["demos"]) == 1
    assert index["demos"][0]["date"] == "2026-10-29"
    demo = json.loads((ROOT / index["demos"][0]["file"]).read_text(encoding="utf-8"))
    assert demo["audio"] == "audio/brief-2026-10-29.mp3"
    assert demo["date"] == "2026-10-29"


def test_old_standalone_url_uses_same_player():
    html = (ROOT / "brief-2026-10-29.html").read_text(encoding="utf-8")
    assert 'url=/demo.html' in html
    assert "<audio" not in html
