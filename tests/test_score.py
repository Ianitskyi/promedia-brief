"""Importance factors: casualties raise a story's rank."""
import pytest

from brief.score import casualties


@pytest.mark.parametrize("text,expected", [
    ("Рятувальники 5 днів розбирали завали: загинули 9 людей", (9, 0)),
    ("У Києві 21 людина постраждала, одна – загинула", (1, 21)),
    ("Внаслідок удару загинули троє працівників", (3, 0)),
    ("Двоє загиблих, п'ятеро травмованих", (2, 5)),
    ("Є загиблі та поранені", (1, 0)),
    ("Кабмін ухвалив постанову про компенсації", (0, 0)),
])
def test_casualties(text, expected):
    assert casualties(text) == expected


def test_more_casualties_rank_higher(make, editorial):
    import datetime as dt

    from brief.score import factors, importance

    now = dt.datetime(2026, 10, 20, 18, 0, tzinfo=dt.timezone.utc)
    sc = editorial["scoring"]

    def score(title):
        it = make(1, title)
        cl = {"item_ids": [it["id"]], "independent_sources": 1, "primary_region": None}
        return importance(factors(cl, {it["id"]: it}, now, sc), sc["weights"])

    few = score("Унаслідок обстрілу поранені двоє людей")
    many = score("Унаслідок обстрілу загинули 12 людей, поранені 40")
    assert many > few
