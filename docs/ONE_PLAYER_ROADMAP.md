# BRIEF product rollout: one player, evolving edition source

## Stage 1 — current pilot (October 2026)
- Exactly one featured audio player on the homepage, not a separate promo card for each release.
- The player reads the single featured item from `demo/index.json`.
- New test edition **replaces** the featured edition, keeping the same card and the same text/source detail link.
- Old audio may stay as archives, but never appears as a second featured player.
- Current featured demo: 29 October 2026; generated with ElevenLabs Yevhen and Yaroslava.
- Editorial/fact-check approval and quality verification remain explicit, not silently assumed.

## Stage 2 — daily BRIEF app
- The same UI player reads a published daily edition, updated on a regular editorial schedule.
- A daily edition supersedes the previous day in the featured player.
- The editorial source trail remains available; avoid duplicate parallel player experiences.

## Stage 3 — individually personalised BRIEF
- When budget permits, generate editions per subscriber based on their explicit interests, preferred topics, locations, duration and sources.
- The same player plays the subscriber's personalised edition; do not add a second player.
- Clear fallback to editorially prepared daily national edition, subject to source verification.
- Estimate generation costs and consent before enabling per-user TTS at scale.

## Interface regression rule
Any publishing code that appends a new player/promo to the homepage, rather than updating the one existing player's data, is a regression.
