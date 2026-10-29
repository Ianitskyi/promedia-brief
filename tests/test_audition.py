from pathlib import Path

import pytest

from brief.audition import SCRIPT, MALE_ID, FEMALE_ID, parse_script, audition


def test_voices_and_archived_spoken_draft():
    assert MALE_ID == "TEyBWD5tAHAWqAGEv6yI"
    assert FEMALE_ID == "0ZQZuw8Sn4cU0rN1Tm2K"
    parts = parse_script(SCRIPT.read_text(encoding="utf-8"))
    assert len(parts) == 16
    assert parts[0][0] == "Yaroslava"
    assert parts[2][0] == "Yevhen"
    assert "Загинула" in parts[2][1]
    assert "вдарили по селу на Харківщині:" not in parts[2][1]
    assert parts[-1][0] == "Yaroslava"


def test_audition_requires_paid_consent(monkeypatch, tmp_path):
    monkeypatch.delenv("BRIEF_ALLOW_PAID_TTS", raising=False)
    with pytest.raises(RuntimeError, match="BRIEF_ALLOW_PAID_TTS"):
        audition(tmp_path / "demo.mp3")


def test_dated_source_script_is_loaded():
    from brief.audition import load_audition_script
    parts, date = load_audition_script(Path("docs/tts/brief-2026-10-29.json"))
    assert date == "2026-10-29"
    assert len(parts) == 10
    assert parts[0][0] == "Yaroslava"
    assert parts[2][0] == "Yevhen"
    assert "Чотирнадцять людей загинули" in parts[2][1]
    assert parts[-1][0] == "Yaroslava"
