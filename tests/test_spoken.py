"""Daily spoken edition: Claude's retelling is checked claim by claim; budget; one player."""
import json
import shutil

import pytest

from brief import featured, review, spoken

from test_audio import approved  # noqa: F401  (fixture)

DATE = "2026-10-20"
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


@pytest.fixture
def root(approved, monkeypatch):  # noqa: F811
    monkeypatch.setattr(review, "EDITIONS", approved / "editions")
    monkeypatch.setattr(spoken, "EDITIONS", approved / "editions")
    monkeypatch.setattr(spoken, "USAGE", approved / "data" / "tts-usage.json")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    return approved


def _stories(root):
    a = json.loads((root / "editions" / DATE / "approved.json").read_text())
    return [s for s in a["segments"] if s["kind"] == "story" and s["block"] in ("national", "regional")]


def _claude(answer):
    return lambda *a, **k: (answer, {"model": "test"})


def test_checked_retelling_is_used_and_invented_facts_fall_back(root, monkeypatch):
    nat, reg = _stories(root)[:2]
    monkeypatch.setattr(spoken, "ask_claude", _claude({
        "teaser": "компенсації за зруйноване житло",
        "stories": [
            {"story_ids": [nat["id"]], "title": "Компенсації",
             "text": "Уряд виділив 2,5 млрд гривень на компенсації за зруйноване житло. Рішення ухвалили на засіданні."},
            # 400 children is not in the source: this retelling must not be read
            {"story_ids": [reg["id"]], "title": "Садок", "text": "У Луцьку відкрили підземний садок на 400 дітей."},
        ]}))
    s = spoken.build(DATE, budget=5000)
    stories = [seg for seg in s["segments"] if seg["kind"] == "story"]
    assert stories[0]["retold"] and stories[0]["sentences"][0]["text"].startswith("Уряд виділив 2,5 млрд")
    assert stories[0]["sources"] == nat["sources"]
    bad = next(seg for seg in stories if seg["from_stories"] == [reg["id"]])
    assert not bad["retold"] and [x["text"] for x in bad["sentences"]] == [x["text"] for x in reg["sentences"]]
    assert any("«400»" in p for r in s["log"]["rejected"] for p in r["problems"])
    left = [seg["id"] for seg in _stories(root)[2:]]
    assert s["log"]["left_out"] == left and len(stories) == 2  # what Claude left out stays out
    assert s["segments"][0]["sentences"][0]["text"] == \
        "Це BRIEF. Головне за двадцяте жовтня: компенсації за зруйноване житло."
    assert "сайті BRIEF" in s["segments"][-1]["sentences"][0]["text"]
    assert review.load_script(DATE, "spoken")["script_sha256"] == s["script_sha256"]


@pytest.mark.parametrize("text,problem", [
    ("Сьогодні уряд виділив 2,5 млрд гривень на компенсації.", "відносне слово часу"),
    ("Уряд Франції виділив 2,5 млрд гривень на компенсації.", "Франції"),
    ("Прем'єр сказав: «це історичне рішення».", "quote"),
])
def test_check_rejects_relative_time_new_names_and_quotes(text, problem):
    ev = {"a": "Уряд виділив 2,5 млрд гривень на компенсації. Рішення ухвалили на засіданні уряду."}
    assert any(problem in p for p in spoken.check_text(text, ev))
    assert spoken.check_text("Уряд виділив 2,5 млрд гривень на компенсації.", ev) == []


def test_merged_stories_may_not_add_up_figures():
    ev = {"a": "У Дніпрі загинули 3 людини.", "b": "У Харкові загинули 3 людини."}
    assert spoken.check_text("Загалом загинули 3 людини в Дніпрі та 3 у Харкові.", ev, merged=True)
    assert not spoken.check_text("У Дніпрі загинули 3 людини. У Харкові — теж 3.", ev, merged=True)


def test_teaser_with_numbers_or_unknown_names_is_dropped(root, monkeypatch):
    nat = _stories(root)[0]
    monkeypatch.setattr(spoken, "ask_claude", _claude({"teaser": "2,5 млрд на житло", "stories": [
        {"story_ids": [nat["id"]], "title": "Компенсації", "text": "Уряд виділив 2,5 млрд гривень на компенсації."}]}))
    s = spoken.build(DATE, budget=5000)
    assert s["segments"][0]["sentences"][0]["text"] == "Це BRIEF. Головне за двадцяте жовтня."
    assert not spoken.check_teaser("рішення Нацбанку", {"a": "Уряд виділив гроші."})


def test_without_api_key_the_approved_sentences_are_read(root, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    s = spoken.build(DATE, budget=5000)
    assert s["retold"] == 0 and s["stories"] == len(_stories(root))
    assert s["log"]["llm_error"] == "no ANTHROPIC_API_KEY"
    p = root / "editions" / DATE / "approved.json"
    a = json.loads(p.read_text())
    story = next(seg for seg in a["segments"] if seg["kind"] == "story")
    story["sentences"][0]["text"] = "Сьогодні " + story["sentences"][0]["text"]
    a["script_sha256"] = review.script_hash({"segments": a["segments"]})
    p.write_text(json.dumps(a, ensure_ascii=False))
    s = spoken.build(DATE, budget=5000)
    assert s["log"]["dropped_relative_time"] == [story["id"]]  # «сьогодні» is wrong when heard later


def test_budget_shares_the_rest_of_the_month_and_cuts_the_least_important(root, monkeypatch):
    cfg = {"monthly_credits": 30000, "reserve": 0.1, "credits_per_char": 1.0}
    assert spoken.day_budget("2026-11-01", cfg, {}) == 900  # 27 000 / 30 days
    assert spoken.day_budget("2026-11-30", cfg, {"2026-11": {"characters": 26000}}) == 1000
    assert spoken.day_budget("2026-11-30", cfg, {"2026-11": {"characters": 30000}}) == 0
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    full = spoken.build(DATE, budget=100000)
    short = spoken.build(DATE, budget=1)
    assert short["stories"] == 2 < full["stories"]  # min_stories keeps an edition audible
    assert short["log"]["cut_for_budget"]
    assert spoken.record_usage(DATE, 800, "elevenlabs") == 800
    assert spoken.record_usage(DATE, 900, "elevenlabs") == 900  # a re-render replaces the day's count


def test_tampered_spoken_script_is_refused(root, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    spoken.build(DATE, budget=5000)
    p = root / "editions" / DATE / "spoken.json"
    d = json.loads(p.read_text())
    d["segments"][1]["sentences"][0]["text"] = "Вигадана новина."
    p.write_text(json.dumps(d, ensure_ascii=False))
    with pytest.raises(review.ApprovalError, match="modified"):
        review.load_script(DATE, "spoken")


@needs_ffmpeg
def test_daily_edition_replaces_the_one_player(root, cli, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    cli(root, "spoken", "--date", DATE, "--no-llm", "--budget", "5000")
    cli(root, "render", "--date", DATE, "--provider", "mock", "--script", "spoken", "--variant", "daily")
    m = json.loads((root / "editions" / DATE / "render-daily.json").read_text())
    assert m["script"] == "spoken"
    monkeypatch.setattr(featured, "EDITIONS", root / "editions")
    monkeypatch.setattr(featured, "DEMO", root / "demo")
    monkeypatch.setattr(featured, "ROOT", root)
    with pytest.raises(featured.FeatureError, match="mock"):
        featured.feature(DATE)
    m.update(provider="elevenlabs")
    (root / "editions" / DATE / "render-daily.json").write_text(json.dumps(m))
    with pytest.raises(featured.FeatureError, match="audio check"):
        featured.feature(DATE)
    m["asr"] = {"mean_cer": 0.05, "failed": []}
    (root / "editions" / DATE / "render-daily.json").write_text(json.dumps(m))
    (root / "demo").mkdir(exist_ok=True)
    (root / "demo" / "2026-10-19-daily.mp3").write_bytes(b"old")
    (root / "demo" / "2026-10-29-demo-elevenlabs.json").write_text("{}")
    featured.feature(DATE)
    idx = json.loads((root / "demo" / "index.json").read_text())
    assert [d["id"] for d in idx["demos"]] == [f"{DATE}-daily"]
    d = json.loads((root / idx["demos"][0]["file"]).read_text())
    assert (root / d["audio"]).exists() and d["segments"][0]["kind"] == "intro" and d["asr_mean_cer"] == 0.05
    assert not (root / "demo" / "2026-10-19-daily.mp3").exists()  # yesterday's daily audio is gone
    assert (root / "demo" / "2026-10-29-demo-elevenlabs.json").exists()  # hand-made demos stay
