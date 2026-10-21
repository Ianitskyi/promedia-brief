"""8. TTS chunking, 9. audio assembly, 10. resume after failure, publish gate."""
import json
import shutil
import subprocess

import pytest

from brief import tts
from brief.speech import cardinal, date_words, speech_text, speech_warnings, transliterate_latin
from brief.tts.chunk import chunk_text

from conftest import write_pool
from test_script import _pool

needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")

TEXT = ("Перше речення новини. Друге речення, у якому є кома, ще одна кома і досить багато слів для перевірки. "
        "Третє речення! Четверте речення? П'яте речення про «цитату». ") * 6


@pytest.mark.parametrize("limit", [40, 120, 500, 5000])
def test_chunks_preserve_text_and_order(limit):
    chunks = chunk_text(TEXT, limit)
    assert " ".join(chunks).split() == TEXT.split()
    assert all(len(c) <= limit for c in chunks)


def test_long_sentence_is_split_at_clauses():
    s = "Довге речення, " * 30 + "кінець."
    chunks = chunk_text(s, 100)
    assert len(chunks) > 1 and all(len(c) <= 100 for c in chunks)
    assert chunks[0].endswith(",")


def test_byte_measure_for_cyrillic():
    chunks = chunk_text(TEXT, 200, measure=lambda x: len(x.encode("utf-8")))
    assert all(len(c.encode("utf-8")) <= 200 for c in chunks)


def test_speech_layer():
    assert date_words("2026-10-20") == "двадцяте жовтня"
    assert date_words("2026-10-31") == "тридцять перше жовтня"
    assert cardinal(21) == "двадцять один" and cardinal(2_500_000) == "два мільйони п'ятсот тисяч"
    out = speech_text("ЗСУ: 30% і 1 200 грн. BRIEF.", spell_digits=True)
    assert out == "зе-ес-у: тридцять відсотків і одна тисяча двісті гривень. Бріф."
    assert transliterate_latin("Ford") == "форд"
    assert any("латиниця" in w for w in speech_warnings("Компанія Acme Corp заявила"))


def test_paid_providers_refuse_without_approval(monkeypatch):
    monkeypatch.delenv("BRIEF_ALLOW_PAID_TTS", raising=False)
    for name in ("google", "azure", "openai", "elevenlabs"):
        with pytest.raises(tts.TTSError, match="paid API"):
            tts.guard_cost(tts.get(name), 6000)
    monkeypatch.setenv("BRIEF_ALLOW_PAID_TTS", "1")
    monkeypatch.setenv("BRIEF_MAX_TTS_USD", "0.10")
    with pytest.raises(tts.TTSError, match="exceeds"):
        tts.guard_cost(tts.get("google"), 6000)  # 6000 chars × $30/1M = $0.18
    assert tts.guard_cost(tts.get("mock"), 10**7) == 0


@pytest.fixture
def approved(tmp_root, make, cli):
    write_pool(tmp_root, "2026-10-20", _pool(make))
    cli(tmp_root, "draft", "--date", "2026-10-20")
    p = tmp_root / "editions" / "2026-10-20" / "draft.json"
    d = json.loads(p.read_text())
    for seg in d["segments"]:
        for s in seg["sentences"]:
            if s["status"] == "needs_review":
                s["editor_confirmed"] = True
    p.write_text(json.dumps(d, ensure_ascii=False))
    cli(tmp_root, "approve", "--date", "2026-10-20", "--reviewer", "test")
    return tmp_root


def _probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=channels,sample_rate",
                        "-of", "json", str(path)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


@needs_ffmpeg
def test_render_assembles_every_segment_and_full_edition(approved, cli):
    cli(approved, "render", "--date", "2026-10-20", "--provider", "mock")
    m = json.loads((approved / "editions" / "2026-10-20" / "render.json").read_text())
    a = json.loads((approved / "editions" / "2026-10-20" / "approved.json").read_text())
    expected = [s["id"] for s in a["segments"] if s["sentences"]]
    assert [s["id"] for s in m["segments"]] == expected
    for seg in m["segments"]:
        assert seg["duration_sec"] > 0 and (approved / seg["file"]).exists()
    full = _probe(approved / m["full"]["file"])
    assert full["streams"][0]["channels"] == 1 and int(full["streams"][0]["sample_rate"]) == 44100
    # full = sonic intro + segments + bumper + outro, so it is longer than the spoken national part alone
    assert float(full["format"]["duration"]) > sum(s["duration_sec"] for s in m["segments"] if s["block"] == "national")
    assert m["script_sha256"] == a["script_sha256"] and m["api_calls"] > 0


@needs_ffmpeg
def test_failed_render_resumes_from_cache(approved, cli):
    # First run: the provider dies after 3 calls (simulated outage).
    r = cli(approved, "render", "--date", "2026-10-20", "--provider", "mock", check=False,
            env_extra={"BRIEF_MOCK_FAIL_AFTER": "3"})
    assert r.returncode != 0
    assert not (approved / "editions" / "2026-10-20" / "render.json").exists()  # no partial manifest
    cached = list((approved / "editions" / "2026-10-20" / ".tts-cache").glob("*.wav"))
    assert len(cached) == 3 and not list((approved / "editions" / "2026-10-20" / ".tts-cache").glob("*.part.*"))
    cli(approved, "render", "--date", "2026-10-20", "--provider", "mock")
    m = json.loads((approved / "editions" / "2026-10-20" / "render.json").read_text())
    total = sum(x["chunks"] for seg in m["segments"] for x in seg["sentences"])
    assert m["cached_chunks"] >= 3 and m["api_calls"] + m["cached_chunks"] == total


@needs_ffmpeg
def test_publish_refuses_mock_and_tampering(approved, cli):
    r = cli(approved, "publish", "--date", "2026-10-20", check=False)
    assert r.returncode != 0 and "not rendered" in r.stderr
    cli(approved, "render", "--date", "2026-10-20", "--provider", "mock")
    r = cli(approved, "publish", "--date", "2026-10-20", check=False)
    assert r.returncode != 0 and "mock placeholder" in r.stderr
    assert not (approved / "editions" / "latest.json").exists()

    ap = approved / "editions" / "2026-10-20" / "approved.json"
    a = json.loads(ap.read_text())
    a["segments"][-1]["sentences"][0]["text"] += " Додане речення."
    ap.write_text(json.dumps(a, ensure_ascii=False))
    r = cli(approved, "publish", "--date", "2026-10-20", "--allow-mock", check=False)
    assert r.returncode != 0 and "modified after approval" in r.stderr


@needs_ffmpeg
def test_publish_writes_public_edition_without_reviewer_name(approved, cli):
    cli(approved, "render", "--date", "2026-10-20", "--provider", "mock")
    cli(approved, "publish", "--date", "2026-10-20", "--allow-mock")
    latest = json.loads((approved / "editions" / "latest.json").read_text())
    e = json.loads((approved / latest["edition"]).read_text())
    assert e["date"] == "2026-10-20" and e["segments"] and "test" not in json.dumps(e["approved"])
    assert "approved_by" not in e
    stories = [s for s in e["segments"] if s["kind"] == "story"]
    assert all(s["sources"] and s["audio"] for s in stories)
    assert (approved / "audio" / "daily.mp3").exists()


def test_prune_removes_editions_older_than_a_week(tmp_root):
    import datetime as dt
    from brief import prune as P

    ed = tmp_root / "editions"
    dates = ("2026-10-01", "2026-10-12", "2026-10-13", "2026-10-20")
    for date in dates:
        (ed / date / "audio").mkdir(parents=True)
        (ed / date / "audio" / "x.mp3").write_bytes(b"mp3")
        (ed / date / "draft.json").write_text("{}")
    (ed / "index.json").write_text(json.dumps({"editions": list(dates)}))
    (ed / "drafts.json").write_text(json.dumps({"drafts": list(dates)}))
    (ed / "latest.json").write_text(json.dumps({"date": "2026-10-12"}))  # stale latest is removed too

    orig = P.EDITIONS
    P.EDITIONS = ed
    try:
        removed = P.prune(7, now=dt.datetime(2026, 10, 20, 12, 0, tzinfo=dt.timezone.utc))
    finally:
        P.EDITIONS = orig
    assert removed == ["2026-10-01", "2026-10-12"]
    assert not (ed / "2026-10-01").exists() and not (ed / "2026-10-12").exists()
    assert (ed / "2026-10-13" / "audio" / "x.mp3").exists() and (ed / "2026-10-20").exists()
    assert json.loads((ed / "index.json").read_text())["editions"] == ["2026-10-13", "2026-10-20"]
    assert json.loads((ed / "drafts.json").read_text())["drafts"] == ["2026-10-13", "2026-10-20"]
    assert not (ed / "latest.json").exists()
