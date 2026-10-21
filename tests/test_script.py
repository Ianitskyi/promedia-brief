"""6. No unsupported news in the edition, 7. script formation, approval gate."""
import json

import pytest

from brief import edition
from brief.factcheck import check_sentence, extract_claims

from conftest import write_pool

SENS = {"patterns": ["загин", "поранен", "обстріл", "удар", "атак"]}
EVIDENCE = {"a": "Кабмін ухвалив постанову. Уряд виділив 2,5 млрд гривень на компенсації 20 жовтня, заявила Юлія Свириденко."}


def test_claims_found_in_sources_are_verified():
    r = check_sentence("Уряд виділив 2,5 млрд гривень на компенсації, заявила Юлія Свириденко.", EVIDENCE, 1, SENS)
    assert r["status"] == "verified"
    assert {c["type"] for c in r["claims"]} >= {"number", "name"}
    assert all(c["found_in"] == ["a"] for c in r["claims"])


@pytest.mark.parametrize("sentence", [
    "Уряд виділив 3,5 млрд гривень на компенсації.",          # wrong number
    "Уряд виділив 2,5 млрд гривень, заявив Денис Шмигаль.",    # name not in sources
    "Прем'єрка заявила: «Ми допоможемо всім».",               # invented quote
    "Рішення ухвалили 20 листопада.",                          # wrong month
])
def test_invented_details_are_unsupported(sentence):
    assert check_sentence(sentence, EVIDENCE, 1, SENS)["status"] == "unsupported"


def test_sensitive_single_source_needs_editor():
    ev = {"a": "Унаслідок обстрілу Херсона поранені троє людей."}
    assert check_sentence("Унаслідок обстрілу Херсона поранені троє людей.", ev, 1, SENS)["status"] == "needs_review"
    assert check_sentence("Унаслідок обстрілу Херсона поранені троє людей.", ev, 2, SENS)["status"] == "verified"


def test_old_year_is_flagged():
    ev = {"a": "Під час боїв 4 вересня 2024 року загинув воїн."}
    r = check_sentence("Під час боїв 4 вересня 2024 року загинув воїн.", ev, 2, SENS, current_year=2026)
    assert r["status"] == "needs_review" and any("2024" in x for x in r["reasons"])


def test_extract_claims_types():
    types = {c["type"] for c in extract_claims("У середу Віталій Кличко заявив: «Мости працюють», ремонт коштуватиме 1 200 гривень.")}
    assert types == {"name", "quote", "number", "date"}


@pytest.mark.parametrize("title,ok", [
    ("Росіяни обстріляли Херсон: поранені троє людей", True),
    ("Reuters: Віткофф поїде до Норвегії", False),        # label-style
    ("Що відомо про удар по Києву?", False),               # question
    ("Головне за день", False),                            # too short
    ("Росіяни атакували «Епіцентр» у Первомайську (оновлено)", True),
])
def test_headline_sentence(title, ok):
    h = edition.headline_sentence(title)
    assert (h is not None) == ok
    if ok:
        assert h.endswith(".") and "(оновлено)" not in h


def test_lead_sentences_skip_fragments_and_background():
    item = {"title": "Норвегія запровадила новий пакет санкцій проти Росії",
            "description": ", який відповідає 21-му пакету санкцій ЄС. Нагадаємо, раніше ЄС ухвалив пакет. "
                           "«Ворог знову атакував об'єкт енергетики. Є пошкодження», — повідомили в ОВА. "
                           "Санкції охоплюють енергетичний і фінансовий сектори Росії."}
    out = edition.lead_sentences(item, 2, 60)
    assert out == ["Норвегія запровадила новий пакет санкцій проти Росії.",
                   "Санкції охоплюють енергетичний і фінансовий сектори Росії."]


def test_spoken_list_and_names():
    assert edition.spoken_list(["A", "B"]) == "A, B"
    assert edition.spoken_list(["A", "B", "C", "D", "E"]) == "A, B, C та ще 2 видання"
    assert edition.spoken_name("Zaholovok.com.ua (Закарпаття. Про головне)", {}) == "Zaholovok.com.ua"


def _pool(make):
    nat = dict(geography="national")
    items = [
        make(1, "Кабмін ухвалив постанову про компенсації за зруйноване житло",
             "Уряд виділив 2,5 млрд гривень на компенсації. Рішення ухвалили на засіданні уряду.",
             published="2026-10-20T10:00:00+00:00", **nat),
        make(2, "Уряд виділив 2,5 млрд гривень на компенсації за житло",
             "Кабмін ухвалив постанову про компенсації за зруйноване житло.", source="LB.ua", source_id="lb",
             url="https://lb.ua/news/2", published="2026-10-20T10:30:00+00:00", **nat),
        make(3, "У Луцьку відкрили новий укриття-садок для дітей",
             "У Луцьку відкрили підземний дитячий садок на 140 дітей.", source="Волинь Оnline", source_id="map-1",
             geography="regional", region="volyn", url="https://volynonline.com/1", published="2026-10-20T11:00:00+00:00"),
        make(4, "Під Ковелем рятувальники ліквідували пожежу на складі",
             "На Ковельщині ДСНС ліквідувала пожежу на складі площею 300 квадратних метрів.", source="Нове життя",
             source_id="map-2", geography="regional", region="volyn", url="https://novezittya.com.ua/2",
             published="2026-10-20T12:00:00+00:00"),
    ]
    return items


@pytest.fixture
def drafted(tmp_root, make, cli):
    write_pool(tmp_root, "2026-10-20", _pool(make))
    cli(tmp_root, "draft", "--date", "2026-10-20")
    return tmp_root


def _draft(root):
    return json.loads((root / "editions" / "2026-10-20" / "draft.json").read_text())


def _save(root, d):
    (root / "editions" / "2026-10-20" / "draft.json").write_text(json.dumps(d, ensure_ascii=False))


def test_draft_structure_attribution_and_disclosure(drafted):
    d = _draft(drafted)
    kinds = [s["kind"] for s in d["segments"]]
    assert kinds[0] == "intro" and kinds[-1] == "outro" and "transition" in kinds
    intro = " ".join(s["text"] for s in d["segments"][0]["sentences"])
    assert "Білого списку" in intro and "Мапи рекомендованих медіа" in intro and "сайті BRIEF" in intro
    stories = [s for s in d["segments"] if s["kind"] == "story"]
    nat = [s for s in stories if s["block"] == "national"]
    assert len(nat) == 1  # two outlets, one event
    assert nat[0]["sentences"][0]["text"].startswith("Українська правда повідомляє: ")
    assert {x["name"] for x in nat[0]["sources"]} == {"Українська правда", "LB.ua"}
    assert any(s["block"] == "local:volyn" for s in stories)
    for seg in stories:  # every sentence traces back to sources
        for s in seg["sentences"]:
            assert s["status"] in ("verified", "needs_review")
            for c in s.get("claims", []):
                assert c["found_in"]
    assert d["script_sha256"] == edition.script_hash(d)
    assert (drafted / "editions" / "2026-10-20" / "draft.md").exists()
    assert json.loads((drafted / "editions" / "drafts.json").read_text())["drafts"] == ["2026-10-20"]


def test_editor_cannot_approve_invented_fact(drafted, cli):
    d = _draft(drafted)
    story = next(s for s in d["segments"] if s["kind"] == "story" and s["block"] == "national")
    story["sentences"][1]["text"] = "Уряд виділив 7 млрд гривень на компенсації."
    _save(drafted, d)
    r = cli(drafted, "approve", "--date", "2026-10-20", "--reviewer", "editor", check=False)
    assert r.returncode != 0 and "непідтверджено" in r.stderr
    assert not (drafted / "editions" / "2026-10-20" / "approved.json").exists()


def test_approval_records_reviewer_and_exact_text(drafted, cli):
    d = _draft(drafted)
    for seg in d["segments"]:
        for s in seg["sentences"]:
            if s["status"] == "needs_review":
                s["editor_confirmed"] = True
    _save(drafted, d)
    r = cli(drafted, "approve", "--date", "2026-10-20", "--reviewer", "editor", "--expected-hash", "deadbeef", check=False)
    assert r.returncode != 0 and "script changed" in r.stderr
    cli(drafted, "approve", "--date", "2026-10-20", "--reviewer", "editor", "--expected-hash", d["script_sha256"][:12])
    a = json.loads((drafted / "editions" / "2026-10-20" / "approved.json").read_text())
    assert a["approved_by"] == "editor" and a["script_sha256"] == d["script_sha256"]


def test_must_include_story_cannot_be_dropped_silently(drafted, cli):
    d = _draft(drafted)
    for seg in d["segments"]:
        if seg.get("must_include"):
            seg["include"] = False
    _save(drafted, d)
    r = cli(drafted, "check", "--date", "2026-10-20", check=False)
    assert r.returncode == 1 and "обов'язковий сюжет виключено" in r.stdout
