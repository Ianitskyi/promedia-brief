"""News values (owner, 2026-11-17): a disruption for millions outranks one death; coverage counts across clusters."""
from brief import impact
from brief.util import config

CFG = config("editorial.json")["scoring"]["impact"]


def test_bridges_of_a_big_city_have_high_impact_and_one_death_none():
    kyiv = impact.impact("Росіяни вдарили та влучили у Північний та Південний мости Києва", ["kyiv"], 13, CFG)
    moped = impact.impact("Російський дрон атакував на Херсонщині чоловіка на мопеді — він загинув", ["kherson"], 6, CFG)
    assert kyiv > 0.9 and moped == 0.0


def test_outage_schedules_are_routine():
    news = impact.impact("Через атаку РФ без світла залишилися понад 50 тисяч родин", ["odesa"], 9, CFG)
    routine = impact.impact("Графіки вимкнення світла на Одещині: як вимикатимуть світло", ["odesa"], 9, CFG)
    assert routine < news


def test_coverage_is_on_a_log_scale():
    assert impact.coverage_factor(1, 15) == 0 and impact.coverage_factor(20, 15) == 1
    assert impact.coverage_factor(4, 15) < impact.coverage_factor(12, 15) < 1


def _items(titles, source):
    return {f"{source}{n}": {"id": f"{source}{n}", "title": t, "source_id": f"{source}{n}"} for n, t in enumerate(titles)}


def test_clusters_about_one_subject_share_coverage_without_chaining():
    a = _items(["Окупанти заявили про удар по Кримському мосту"] * 4, "a")
    b = _items(["Супутникові знімки: пошкоджено арку на Кримському мосту"] * 3, "b")
    c = _items(["У Харкові дрон влучив у будинок"] * 3, "c")
    filler = _items([f"Новина про різне номер {n}" for n in range(200)], "f")
    items = {**a, **b, **c, **filler}
    clusters = [{"id": "A", "item_ids": list(a)}, {"id": "B", "item_ids": list(b)}, {"id": "C", "item_ids": list(c)}] + \
               [{"id": f"F{n}", "item_ids": [k]} for n, k in enumerate(filler)]
    impact.families(clusters, items, CFG)
    A, B, C = clusters[:3]
    assert "B" in A["related"] and A["coverage"] == 7
    assert "C" not in A["related"] and C["coverage"] == 3
