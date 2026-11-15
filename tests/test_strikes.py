"""Strike digest: one summary story with a verified, never-inflated sum (brief/strikes.py)."""
from brief import strikes
from brief.strikes import clause_figure, lead_sentences, pick

DATE = "2026-11-15"
T = "2026-11-15T05:30:00+00:00"


def test_clause_counts():
    assert clause_figure("Одна людина загинула") == ("killed", 1)
    assert clause_figure("14 постраждали") == ("injured", 14)
    assert clause_figure("шестеро людей дістали поранення") == ("injured", 6)
    assert clause_figure("Внаслідок атаки двоє чоловіків 42 і 45 років загинули") == ("killed", 2)
    assert clause_figure("Жінка віком 55 років перебуває у важкому стані, її госпіталізували") is None or \
        clause_figure("Жінка віком 55 років перебуває у важкому стані, її госпіталізували")[1] != 55


def test_doubtful_clauses_are_skipped():
    assert clause_figure("загинули двоє і поранені п'ятеро") is None          # both kinds: can't tell
    assert clause_figure("з початку року загинули 120 цивільних") is None      # longer period
    assert clause_figure("загинули троє військових") is None                   # not civilians
    assert clause_figure("ударили 90 дронами по 14 населених пунктах") is None  # no casualties
    assert clause_figure("поранені 3 або 4 людини") is None                    # two numbers


def test_pick_takes_confirmed_largest_or_smallest():
    f = lambda n, i: {"n": n, "item_id": i}
    assert pick([f(13, "a"), f(32, "b"), f(32, "c")])[0]["n"] == 32  # 32 confirmed twice
    assert pick([f(3, "a"), f(14, "b")])[0]["n"] == 3                 # disagree, none confirmed
    assert pick([f(5, "a")])[0]["n"] == 5


def seg(sid, sentence, items):
    return {"id": sid, "title": sentence, "sentences": [{"text": sentence}],
            "sources": [{"item_id": i, "name": "Медіа", "url": f"https://x/{i}", "published_at": T} for i in items]}


def test_digest_merges_and_never_adds_within_a_region():
    evidence = {
        "a": "Росіяни атакували Харків дронами. Одна людина загинула, 14 постраждали, серед них четверо дітей.",
        "b": "Через російські обстріли на Харківщині постраждали 14 людей.",  # same people again
        "c": "РФ вдарила по Запоріжжю: 32 людини поранені.",
        "d": "Російський удар по Запоріжжю 15 листопада: поранені 32 людини.",
        "e": "Ворог атакував Ізраїль, загинули 5 людей.",  # not a region of Ukraine
    }
    stories = [seg("s1", "Удар по Харкову.", ["a", "b"]), seg("s2", "Удар по Запоріжжю.", ["c", "d"]),
               seg("s3", "Новина про економіку.", []), seg("s4", "Удар по Ізраїлю.", ["e"])]
    by_id = {s["id"]: s for s in stories}
    items = [{"ids": [s["id"]], "title": s["title"], "lines": [s["sentences"][0]["text"]],
              "sources": s["sources"], "rank": n, "retold": False} for n, s in enumerate(stories)]
    out, log = strikes.build_digest(items, by_id, evidence, DATE)
    assert log["merged"] and log["killed"] == 1 and log["injured"] == 14 + 32
    digest = out[0]
    assert digest["lines"][0] == ("Унаслідок російських ударів за добу в Україні загинула щонайменше 1 людина, "
                                  "ще щонайменше 46 людей поранено.")
    assert "s3" not in digest["ids"] and any(it["ids"] == ["s3"] for it in out)


def test_old_reports_are_not_counted():
    evidence = {"a": "Росіяни вдарили по Сумах 3 листопада: загинули двоє людей.",
                "b": "Росіяни атакували Херсон, двоє людей поранені."}
    stories = [seg("s1", "x", ["a"]), seg("s2", "y", ["b"])]
    result, log = strikes.tally(stories, evidence, DATE)
    assert result["killed"] == 0 and result["injured"] == 2
    assert any("інша дата" in x["skipped"] for x in log)


def test_no_digest_for_a_single_strike_story():
    evidence = {"a": "Росіяни атакували Харків. Одна людина загинула."}
    s = seg("s1", "Удар по Харкову.", ["a"])
    items = [{"ids": ["s1"], "title": "x", "lines": ["x"], "sources": s["sources"], "rank": 0, "retold": False}]
    assert strikes.build_digest(items, {"s1": s}, evidence, DATE) == (items, None)


def test_lead_grammar():
    r = lambda k, i: {"killed": k, "injured": i, "regions": {}}
    assert lead_sentences(r(3, 0)) == ["Унаслідок російських ударів за добу в Україні загинули щонайменше 3 людини."]
    assert lead_sentences(r(0, 21)) == ["Унаслідок російських ударів за добу в Україні поранено щонайменше 21 людину."]
    assert lead_sentences(r(0, 0)) == []
