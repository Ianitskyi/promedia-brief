# BRIEF by ProMedia

Audio-first MVP for a personalised daily briefing built from trusted Ukrainian journalism.

## Product principle

**Listen first. Read at the source.**

BRIEF does not republish full newsroom articles. The MVP uses openly available materials from media included in the IMI White List and the Recommended Media Map (IMI + Detector Media), creates short audio summaries, clearly attributes sources, and sends users to the original publication.

## MVP 0.1

- free pilot
- audio-first daily briefing
- topic personalisation
- source attribution
- links to original journalism
- no paywalled content
- no revenue sharing yet
- no full-text republication
- cost-recovery pricing only if infrastructure costs require it

Site: https://brief.promedia.report (GitHub Pages; DNS on Cloudflare: `CNAME brief → ianitskyi.github.io`).

## How it works (0.2)

No generative AI writes the news. The pipeline selects, attributes and voices text published by eligible newsrooms, and an editor approves every edition.

```
collect → dedupe → cluster → score → extractive script + fact trace → editor review → approve → TTS → audio check → publish
```

- Architecture, plan and costs: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Audit of the previous state: [`docs/AUDIT.md`](docs/AUDIT.md)
- TTS comparison and method: [`docs/TTS.md`](docs/TTS.md)
- Editor guide (Ukrainian): [`docs/EDITOR_GUIDE.md`](docs/EDITOR_GUIDE.md)
- Sources: [`config/sources.json`](config/sources.json) (IMI White List), [`config/media_map.json`](config/media_map.json) (Recommended Media Map snapshot)
- Editorial settings (TEST values, pending approval): [`config/editorial.json`](config/editorial.json), pronunciation: [`config/lexicon.json`](config/lexicon.json)

## Run locally

```bash
pip install -r requirements-dev.txt          # + ffmpeg for audio
python -m brief collect                      # fetch feeds into data/raw/<Kyiv date>.json
python -m brief draft --date 2026-10-20      # editions/<date>/draft.json + draft.md
python -m http.server 8080                   # open /review.html and /index.html
python -m brief check --date 2026-10-20      # re-check an edited draft
python -m brief approve --date 2026-10-20 --reviewer NAME --expected-hash SHA
BRIEF_PIPER_MODEL=/path/uk_UA-ukrainian_tts-medium.onnx python -m brief render --date 2026-10-20 --provider piper
python -m brief verify-audio --date 2026-10-20   # optional, needs faster-whisper
python -m brief publish --date 2026-10-20
python -m brief prune --keep-days 7          # delete editions older than a week
python -m pytest -q                          # no network, no paid APIs
```

Paid TTS providers refuse to run unless `BRIEF_ALLOW_PAID_TTS=1` and the estimated cost is below `BRIEF_MAX_TTS_USD`.

## GitHub Actions

| Workflow | When | What |
|---|---|---|
| Collect BRIEF source pool | hourly | merges new RSS items into today's pool |
| Draft BRIEF edition | daily | builds the draft for review (no TTS, nothing published) |
| Approve and render BRIEF edition | manual, editors only | approval (re-checks), TTS, audio check, publish |
| Compare TTS voices | manual | renders the TTS test script with chosen providers, ASR accuracy + mp3 for listening |
| Refresh regional source registry | monthly | snapshot of the Recommended Media Map → review branch |
| CI | PRs | tests |

`render-audio.yml` / `scripts/render_audio.py` (hand-written script → Google TTS) are kept as the legacy path; they were never run.

## Status

MVP 0.2: technically ready for editorial testing. Pending decisions: TTS provider (listening test), scoring weights and pilot regions. Editions are kept for 7 days. Until the first approved edition is published, the site shows the 3 October test edition.
