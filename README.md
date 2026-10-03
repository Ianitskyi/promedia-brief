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

## Run locally

```bash
python -m http.server 8080
```

Open `http://localhost:8080`.

## Next technical milestone

1. ingest RSS / structured feeds from eligible media
2. normalize and deduplicate stories
3. cluster coverage of the same event
4. generate source-grounded Ukrainian summaries
5. generate TTS audio
6. build one playable daily edition
7. measure completion rate and source click-through

## Status

MVP prototype. Demo stories are intentionally fictional and must not be treated as current news.
