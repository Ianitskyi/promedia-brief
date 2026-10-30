"""Publish a dated, sourced BRIEF audio edition after a successful synthesis."""
import html
import json
import pathlib
import re
from .audio import duration
from .util import ROOT

DATE = "2026-10-29"
SCRIPT = ROOT / "docs" / "tts" / f"brief-{DATE}.json"
AUDIO = ROOT / "audio" / f"brief-{DATE}.mp3"
PAGE = ROOT / f"brief-{DATE}.html"


def main():
    edition = json.loads(SCRIPT.read_text(encoding="utf-8"))
    if edition.get("date") != DATE:
        raise ValueError("Edition date mismatch")
    if not AUDIO.is_file() or AUDIO.stat().st_size < 20000:
        raise ValueError("Missing or incomplete MP3; refusing publication")
    seconds = duration(AUDIO)
    if seconds < 45:
        raise ValueError("Audio too short for full briefing")
    items = []
    for item in edition["segments"]:
        if item["role"] != "story":
            continue
        if not item.get("sources"):
            raise ValueError("Story missing source")
        urls = []
        for url in item["sources"]:
            if not re.fullmatch(r"https://[a-zA-Z0-9.-]+/.+", url):
                raise ValueError("Invalid source URL")
            urls.append(f'<a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener noreferrer">Джерело</a>')
        items.append(f'<li><strong>{html.escape(item["title"])}</strong><p>{html.escape(item["text"])}</p><p class="src">{" · ".join(urls)}</p></li>')
    title = "BRIEF — новини за 29 жовтня 2026"
    page = f"""<!doctype html>
<html lang="uk"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="icon" type="image/svg+xml" href="/favicon.svg"><title>{title}</title>
<style>
:root{{color-scheme:light}}body{{font-family:system-ui,-apple-system,sans-serif;background:#f4f2ec;color:#171717;margin:0}}
main{{max-width:680px;margin:0 auto;padding:26px 20px 100px}}
a{{color:inherit}}.brand{{font-size:24px;font-weight:850;text-decoration:none}}h1{{font-size:clamp(28px,6vw,45px);letter-spacing:-.05em;line-height:1.07}}
.player{{background:#171717;color:white;border-radius:22px;padding:20px;margin:24px 0}}audio{{width:100%}}
ol{{padding-left:25px}}li{{padding:18px 5px;border-bottom:1px solid #d9d6cf}}li strong{{font-size:19px}}li p{{line-height:1.5}}
.src{{font-size:13px;color:#555}}.note{{font-size:13px;color:#666}}
</style></head><body><main>
<a class="brand" href="/">BRIEF.</a><h1>{title}</h1>
<p>Головне з українських медіа. З посиланнями на першоджерела.</p>
<div class="player"><strong>Слухати випуск</strong><p><audio controls preload="metadata" src="/audio/brief-{DATE}.mp3"></audio></p>
<small>Орієнтовно {round(seconds/60)} хвилин · Yevhen та Yaroslava</small></div>
<h2>Новини випуску</h2><ol>{"".join(items)}</ol>
<p class="note">Редакційний аудіовипуск за 29 жовтня 2026 року. Часові слова у новинах стосуються дати випуску.</p>
</main></body></html>"""
    PAGE.write_text(page, encoding="utf-8")
    print(f"{PAGE}: {len(items)} stories; {seconds:.1f}s; {AUDIO.stat().st_size} bytes")


if __name__ == "__main__":
    main()
