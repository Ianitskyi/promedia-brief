"""2. Deduplication, 5. clustering, 4. editorial filtering."""
from brief import cluster as C
from brief.classify import detect_places, excluded, primary_region, topics


def cl(items, editorial, gazetteer):
    return C.cluster(items, editorial["clustering"], gazetteer)


def test_exact_and_same_source_duplicates_removed(make):
    a = make(1, "Кабмін ухвалив постанову про компенсації", url="https://www.pravda.com.ua/news/1/?utm_source=tg")
    b = make(2, "Кабмін ухвалив постанову про компенсації", url="https://pravda.com.ua/news/1")  # same canonical URL
    c = make(3, "Кабмін ухвалив постанову про компенсації", url="https://www.pravda.com.ua/news/1-copy/")  # republished
    d = make(4, "Кабмін ухвалив постанову про компенсації", source="LB.ua", source_id="lb", url="https://lb.ua/news/1")
    kept, removed = C.dedupe([a, b, c, d])
    assert {k["source_id"] for k in kept} == {"pravda", "lb"} and len(kept) == 2
    assert sorted(r["reason"] for r in removed) == ["duplicate-url", "same-source-duplicate"]


def test_same_event_from_different_outlets_is_one_cluster(make, editorial, gazetteer):
    items = [
        make(1, "Російський БпЛА вдарив по «Епіцентру» в Первомайську на Миколаївщині",
             "Унаслідок удару по гіпермаркету «Епіцентр» у Первомайську поранені вісім людей, повідомила ОВА."),
        make(2, "У Первомайську дрон влучив в «Епіцентр»: вісім поранених",
             "Російський безпілотник атакував «Епіцентр» у Первомайську, постраждали вісім людей.",
             source="МикВісті", source_id="map-1", geography="regional", region="mykolaiv",
             url="https://nikvesti.com/news/1", published="2026-10-20T16:00:00+00:00"),
        make(3, "Армія РФ атакувала «Епіцентр» на Миколаївщині, є поранені",
             "Російські війська вдарили по гіпермаркету «Епіцентр» у Первомайську. Поранено вісім людей.",
             source="Укрінформ", source_id="ukrinform", url="https://www.ukrinform.ua/1",
             published="2026-10-20T17:00:00+00:00"),
    ]
    out = cl(items, editorial, gazetteer)
    assert len(out) == 1
    assert out[0]["independent_sources"] == 3
    assert set(out[0]["sources"]) == {"Українська правда", "МикВісті", "Укрінформ"}


def test_different_events_with_shared_words_are_not_merged(make, editorial, gazetteer):
    items = [
        make(1, "Росіяни обстріляли Херсон: поранені троє людей", "Під обстріл потрапив Корабельний район Херсона."),
        make(2, "Росіяни обстріляли Харків: поранені троє людей", "Під обстріл потрапив Новобаварський район Харкова.",
             source="LB.ua", source_id="lb", url="https://lb.ua/2"),
    ]
    assert len(cl(items, editorial, gazetteer)) == 2  # same words, different places


def test_local_outlet_stories_about_its_city_stay_separate(make, editorial, gazetteer):
    kw = dict(source="Полтавська думка", source_id="map-9", geography="regional", region="poltava")
    items = [
        make(1, "У Полтаві автомобіль збив жінку", "Подія сталася у Полтаві на вулиці Соборності.", url="https://pd.ua/1", **kw),
        make(2, "У Полтаві не буде води за низкою адрес", "У Полтаві тимчасово відключать воду.", url="https://pd.ua/2", **kw),
        make(3, "У Полтаві попрощалися із загиблим воїном", "Полтавці попрощалися з захисником у Полтаві.",
             url="https://pd.ua/3", **kw),
    ]
    assert len(cl(items, editorial, gazetteer)) == 3


def test_reports_far_apart_in_time_are_not_merged(make, editorial, gazetteer):
    a = make(1, "Зеленський зустрівся з Віткоффом в Осло", "Президент Зеленський провів переговори з Віткоффом в Осло.")
    b = make(2, "Зеленський зустрівся з Віткоффом в Осло", "Президент Зеленський провів переговори з Віткоффом в Осло.",
             source="NV", source_id="nv", url="https://nv.ua/1", published="2026-10-22T15:00:00+00:00")
    assert len(cl([a, b], editorial, gazetteer)) == 2


def test_places_require_capitalised_names(gazetteer):
    assert detect_places("Удар по Сумах і Сумщині", gazetteer) == {"sumy"}
    assert detect_places("сума виплат зросла, рівно о дев'ятій", gazetteer) == set()
    assert detect_places("Мешканці Луцька і Ковеля", gazetteer) == {"volyn"}


def test_primary_region_ignores_incidental_mentions(make, gazetteer):
    m = make(1, "У Черкасах попрощалися з прикордонником", "Церемонія відбулася на вулиці Богдана Хмельницького в Черкасах.")
    assert primary_region([m], gazetteer) == "cherkasy"
    n = make(2, "Уряд змінив правила вступу до університетів", "У Луцьку вступники вже подали заяви.")
    assert primary_region([n], gazetteer) is None  # region not in any headline


def test_excluded_material(editorial):
    ex = editorial["exclude"]
    assert excluded({"title": "Партнерський матеріал: смартфони", "url": "https://x/1"}, ex)
    assert excluded({"title": "Чому це важливо", "url": "https://x/blogs/1"}, ex)
    assert excluded({"title": "Кабмін ухвалив постанову", "url": "https://x/news/1"}, ex) is None


def test_topics(editorial):
    assert topics("НБУ залишив облікову ставку, інфляція сповільнилась", editorial["topics"])[0] == "Економіка"
    assert "Війна та безпека" in topics("Унаслідок обстрілу поранені двоє людей", editorial["topics"])


def test_likely_same_event_guard_compares_reports_not_whole_clusters(make):
    big = [make(i, f"Санкції Норвегії проти Росії {i}", "Норвегія запровадила санкції.") for i in range(1, 6)]
    other = make(9, "На Сумщині спецпризначенці взяли в полон 29 військових", "Операція ГУР на Сумщині.",
                 url="https://lb.ua/9", source="LB.ua", source_id="lb")
    by_id = {i["id"]: i for i in big + [other]}
    c1 = {"item_ids": [i["id"] for i in big], "regions": []}
    c2 = {"item_ids": [other["id"]], "regions": ["sumy"]}
    assert not C.likely_same_event(c2, c1, by_id)
