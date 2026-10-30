import json
import pytest

from brief.spoken import propose_text, build_proposals


def fake_transport(payload):
    assert "не додавай" in payload["messages"][0]["content"].lower()
    return {"choices": [{"message": {"content": json.dumps({
        "spoken_text": "Міська рада вирішила ремонтувати міст.",
        "notes": "Скорочено канцеляризм."
    })}}]}


def test_proposal_is_plain_json_and_no_api_call():
    text, notes = propose_text(
        "Міською радою було ухвалено рішення про ремонт мосту.",
        "Тестове видання", transport=fake_transport)
    assert text == "Міська рада вирішила ремонтувати міст."
    assert "канцеляризм" in notes


def test_proposal_requires_key_without_mock(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        propose_text("Приклад речення.", "Джерело")


def test_build_requires_explicit_paid_opt_in(monkeypatch):
    monkeypatch.delenv("BRIEF_ALLOW_PAID_REWRITE", raising=False)
    with pytest.raises(RuntimeError, match="BRIEF_ALLOW_PAID_REWRITE"):
        build_proposals("2026-10-22")
