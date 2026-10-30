import json
from brief.spoken import propose_text, SYSTEM


def test_rewrite_context_has_date_of_edition():
    sent = []
    def mock(payload):
        sent.append(payload)
        return {"choices": [{"message": {"content": json.dumps({
            "spoken_text": "Одна жінка загинула сьогодні вночі.",
            "notes": "Головний факт першим"
        })}}]}
    propose_text("Одна жінка загинула.", "Тест",
                 edition_date="2026-10-22", transport=mock)
    body = json.loads(sent[0]["messages"][1]["content"])
    assert body["edition_date"] == "2026-10-22"
    assert "перевернутої піраміди" in SYSTEM
    assert "зазнали поранень" in SYSTEM
    assert "Києві" in SYSTEM
