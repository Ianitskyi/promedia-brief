"""1. RSS processing, 3. dates, 4. source filtering, 10. re-runs after failure (collector)."""
import datetime as dt
import json
import urllib.error

import pytest

from brief import collect, http
from brief.normalize import canonical_url, clean_text, parse_date, split_sentences

from conftest import FIXTURES

SOURCE = {"id": "pravda", "name": "Українська правда", "domains": ["pravda.com.ua"], "geography": "national",
          "feeds": ["https://www.pravda.com.ua/rss/view_mainnews/"], "feed_status": "active"}
NOW = dt.datetime(2026, 10, 20, 21, 0, tzinfo=dt.timezone.utc)  # 00:00 Kyiv, 21 Oct


def feed_bytes():
    return (FIXTURES / "feed_pravda.xml").read_bytes()


def test_parse_feed_normalises_items():
    rows, skipped = collect.parse_feed(feed_bytes(), SOURCE, NOW)
    by_title = {r["title"]: r for r in rows}
    first = by_title["У Херсоні через обстріл постраждали троє людей"]
    assert first["url"] == "https://pravda.com.ua/news/2026/10/20/1000001"  # tracking params stripped
    assert first["description"] == "Унаслідок обстрілу Корабельного району Херсона постраждали троє людей, повідомила ОВА."
    assert first["published_at"] == "2026-10-20T18:30:00+00:00"
    assert first["source_id"] == "pravda" and first["id"]
    assert skipped == {"link outside source domain": 1, "missing title or link": 1}


def test_item_without_date_is_flagged_not_dropped():
    rows, _ = collect.parse_feed(feed_bytes(), SOURCE, NOW)
    nodate = [r for r in rows if r["published_at"] is None]
    assert len(nodate) == 1 and nodate[0]["date_issues"] == ["no-date"]


def test_summary_is_truncated_never_full_text():
    entry = {"title": "Заголовок новини", "link": "https://www.pravda.com.ua/x/", "summary": "Речення тексту. " * 200}
    row, _ = collect.normalize_entry(entry, SOURCE, NOW)
    assert len(row["description"]) <= collect.SUMMARY_LIMIT


@pytest.mark.parametrize("raw,expected", [
    ("Tue, 20 Oct 2026 23:50:00 +0300", "2026-10-20T20:50:00+00:00"),
    ("2026-10-20T20:50:00Z", "2026-10-20T20:50:00+00:00"),
    ("2026-10-20T23:50:00", "2026-10-20T20:50:00+00:00"),  # naive = Kyiv time
    ("not a date", None),
    ("", None),
])
def test_parse_date(raw, expected):
    d = parse_date(raw)
    assert (d.isoformat() if d else None) == expected


def test_future_dates_are_flagged():
    entry = {"title": "Новина з майбутнього", "link": "https://www.pravda.com.ua/f/", "published": "Wed, 21 Oct 2026 12:00:00 +0300"}
    row, _ = collect.normalize_entry(entry, SOURCE, NOW)
    assert "future-date" in row["date_issues"]


def test_items_are_bucketed_by_kyiv_date(tmp_path):
    # 23:50 Kyiv on the 20th is 20:50 UTC; 00:10 Kyiv on the 21st is still the 20th in UTC.
    xml = feed_bytes().replace(b"</channel>", """<item><title>Опівнічна новина про важливе рішення</title>
      <link>https://www.pravda.com.ua/news/2026/10/21/1/</link><pubDate>Wed, 21 Oct 2026 00:10:00 +0300</pubDate></item></channel>""".encode())
    now = dt.datetime(2026, 10, 20, 21, 30, tzinfo=dt.timezone.utc)
    report = collect.run(fetch=lambda url, **k: xml, now=now, sources=[SOURCE], raw_dir=tmp_path)
    p20 = json.loads((tmp_path / "2026-10-20.json").read_text())
    p21 = json.loads((tmp_path / "2026-10-21.json").read_text())
    assert any("1000002" in i["url"] for i in p20["items"])
    assert "Опівнічна новина про важливе рішення" in [i["title"] for i in p21["items"]]
    assert "Опівнічна новина про важливе рішення" not in [i["title"] for i in p20["items"]]
    assert report["errors"] == []


def test_rerun_merges_and_never_loses_items(tmp_path):
    full = feed_bytes()
    collect.run(fetch=lambda url, **k: full, now=NOW, sources=[SOURCE], raw_dir=tmp_path)
    first = json.loads((tmp_path / "2026-10-20.json").read_text())
    # the feed later drops the oldest entry: the pool must keep it
    shorter = full.replace(b"1000001", b"9999999")
    collect.run(fetch=lambda url, **k: shorter, now=NOW + dt.timedelta(hours=1), sources=[SOURCE], raw_dir=tmp_path)
    second = json.loads((tmp_path / "2026-10-20.json").read_text())
    ids_first = {i["id"] for i in first["items"]}
    ids_second = {i["id"] for i in second["items"]}
    assert ids_first <= ids_second
    assert len(ids_second) == len(second["items"])  # no duplicates
    assert len(second["runs"]) == 2


def test_one_failing_feed_does_not_stop_the_run(tmp_path):
    broken = dict(SOURCE, id="broken", name="Зламаний", feeds=["https://broken.example/rss"])

    def fetch(url, **k):
        if "broken" in url:
            raise http.FetchError(url, "HTTP 500")
        return feed_bytes()

    report = collect.run(fetch=fetch, now=NOW, sources=[SOURCE, broken], raw_dir=tmp_path)
    assert len(report["errors"]) == 1 and report["errors"][0]["source"] == "Зламаний"
    assert report["pools"]["2026-10-20"]["items"] > 0


def test_eligible_sources_only_active_with_feeds():
    cfg = {"national_sources": [dict(SOURCE), dict(SOURCE, id="x", feed_status="not-found", feeds=[]),
                                dict(SOURCE, id="y", feed_status="blocked", feeds=["https://y/rss"])]}
    assert [s["id"] for s in collect.eligible_sources(cfg, include_regional=False)] == ["pravda"]


def test_configured_national_sources_match_white_list():
    from brief.util import config

    cfg = config("sources.json")
    names = {s["name"] for s in cfg["national_sources"]}
    assert len(names) == cfg["lists"]["imi_white_list"]["count"] == 18
    for s in cfg["national_sources"]:
        assert s["list"] == "imi_white_list" and s["list_verified_on"] and s["feed_checked_on"]
        assert s["feed_status"] in ("active", "not-found", "blocked")
        assert (s["feed_status"] == "active") == bool(s["feeds"])
        assert s.get("feed_format", "rss") in collect.PARSERS


def test_legacy_pool_items_are_upgraded():
    legacy = {"source": "LB.ua", "title": "Т", "url": "https://lb.ua/news/1?utm_source=x",
              "published_at": "Tue, 20 Oct 2026 23:25:00 +0300", "description": "<b>Опис</b>"}
    up = collect.upgrade_legacy(legacy)
    assert up["id"] and up["source_id"] == "lb" and up["published_at"] == "2026-10-20T20:25:00+00:00"
    assert up["url"] == canonical_url(legacy["url"]) and up["description"] == "Опис"


class _Resp:
    def __init__(self, body):
        self.body = body

    def read(self, n):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_retries_transient_errors_only():
    calls = []

    def opener(req, timeout):
        calls.append(req.full_url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(req.full_url, 503, "busy", {}, None)
        return _Resp(b"ok")

    assert http.fetch("https://x/", opener=opener, sleep=lambda s: None) == b"ok"
    assert len(calls) == 3

    def forbidden(req, timeout):
        calls.append("403")
        raise urllib.error.HTTPError(req.full_url, 403, "no", {}, None)

    calls.clear()
    with pytest.raises(http.FetchError):
        http.fetch("https://x/", opener=forbidden, sleep=lambda s: None)
    assert calls == ["403"]  # access restrictions are never retried or worked around


def test_clean_text_and_sentences():
    assert clean_text("<p>Перше.</p><p>Друге</p> Читати далі →") == "Перше. Друге"
    assert clean_text("в соцмережі X.Віцепрезидентка заявила") == "в соцмережі X. Віцепрезидентка заявила"
    assert clean_text("Валерія Рубаняк вт, 20/10/2026 - 17:47 Під час боїв загинув воїн.") == "Під час боїв загинув воїн."
    assert split_sentences("Президент В. Зеленський прибув у м. Осло. Там він зустрівся з прем'єром. «Це важливо», — сказав він.") == [
        "Президент В. Зеленський прибув у м. Осло.", "Там він зустрівся з прем'єром.", "«Це важливо», — сказав він."]


def test_news_sitemap_source():
    src = dict(SOURCE, id="hromadske", name="hromadske", domains=["hromadske.ua"], feed_format="news-sitemap",
               feeds=["https://hromadske.ua/sitemap/news.xml"])
    body = (FIXTURES / "news_sitemap.xml").read_bytes()
    rows, errors, skipped = collect.collect_source(src, NOW, fetch=lambda url, **k: body)
    assert errors == [] and skipped == {"link outside source domain": 1}
    assert len(rows) == 1
    r = rows[0]
    assert r["title"] == "Перед отриманням мільярдного підряду компанія змінила власника"
    assert r["published_at"] == "2026-10-21T11:58:00+00:00" and r["description"] == ""
    assert r["source_id"] == "hromadske" and r["url"] == "https://hromadske.ua/ukrayina/1-pered-otrymanniam-pidriadu"


def test_feed_shared_by_national_and_map_source_is_collected_once():
    ids = [s["id"] for s in collect.eligible_sources()]
    feeds = [f for s in collect.eligible_sources() for f in s["feeds"]]
    assert "suspilne" in ids
    assert len(feeds) == len(set(feeds))
