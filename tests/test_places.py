"""Stress of village names from Ukrainian Wikipedia (owner, 2026-11-17: «Садо́ве», not «Са́дове»)."""
import json

from brief import places
from brief.speech import apply_stress


def fake_wiki(url, **kw):
    if "list=search" in url:
        return json.dumps({"query": {"search": [{"title": "Садове (Херсонський район)"},
                                                {"title": "Садове (Генічеський район)"},
                                                {"title": "Садове (Сумський район)"}]}}).encode()
    return json.dumps({"query": {"pages": [
        {"title": "Садове (Херсонський район)",
         "extract": "Садо́ве (в минулому — Фалєєвка) — село в Україні, у Херсонській міській громаді Херсонського району Херсонської області."},
        {"title": "Садове (Генічеський район)",
         "extract": "Садо́ве — село в Україні, у Новотроїцькій селищній громаді Генічеського району Херсонської області."},
        {"title": "Садове (Сумський район)", "extract": "Са́дове — село в Україні, Сумської області."},
    ]}}).encode()


def test_settlements_are_found_in_the_nominative():
    assert places.settlements("Поблизу села Садове на Херсонщині дрон атакував мопед; у місті Сміла") == \
        ["Садове", "Сміла"]


def test_stress_comes_from_articles_about_the_same_region():
    stressed, source = places.lookup("Садове", "kherson", get=fake_wiki)
    assert stressed == "Садо́ве" and "wikipedia" in source


def test_the_entry_covers_the_case_forms():
    e = places.entry("Садо́ве")
    marked = apply_stress("біля Садового, у Садовому, село Садове", [e])
    assert marked.count("Садо́в") == 3


def test_only_articles_about_the_region_count():
    stressed, why = places.lookup("Садове", "sumy", get=fake_wiki)
    assert stressed == "Са́дове"
    assert places.lookup("Садове", "lviv", get=fake_wiki)[0] is None
