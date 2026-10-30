"""Regression tests: spoken briefs must not repeat an article headline."""
from brief.edition import lead_sentences


def test_lead_only_reads_annotation_not_headline():
    item = {
        "title": "У місті відкрили новий центр допомоги мешканцям",
        "description": "У місті запрацював центр допомоги мешканцям, де надають безкоштовні консультації. Центр надаватиме консультації для місцевих мешканців щодня.",
    }
    result = lead_sentences(item, 2, 60, opening="lead_only")
    assert len(result) == 2
    assert "відкрили новий центр" not in " ".join(result)
    assert result[0].startswith("У місті запрацював центр")


def test_lead_only_never_falls_back_to_headline():
    item = {
        "title": "У місті відкрили новий центр допомоги мешканцям",
        "description": "Читайте подробиці у нашому матеріалі.",
    }
    assert lead_sentences(item, 2, 60, opening="lead_only") == []


def test_lead_only_can_use_independent_lead_when_headline_is_teaser():
    item = {
        "title": "Що відомо про новий центр допомоги?",
        "description": "У місті запрацював центр допомоги мешканцям, де надають безкоштовні консультації.",
    }
    result = lead_sentences(item, 2, 60, opening="lead_only")
    assert len(result) == 1
    assert result[0].startswith("У місті запрацював")
