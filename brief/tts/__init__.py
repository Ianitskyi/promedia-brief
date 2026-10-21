"""Text-to-speech providers behind one interface.

A provider reads *exactly* the text it is given. Chunking never drops, repeats or
reorders text: `chunk_text` asserts that the chunks re-join to the original.
Paid providers refuse to run unless BRIEF_ALLOW_PAID_TTS=1 is set and the estimated
cost is under BRIEF_MAX_TTS_USD (default 1.00) — no API credits are spent by accident.
"""
import os

from .base import Provider, TTSError
from .chunk import chunk_text

PROVIDERS = {}


def register(cls):
    PROVIDERS[cls.name] = cls
    return cls


def get(name, **kwargs) -> Provider:
    from . import azure, elevenlabs, google, mock, openai, piper  # noqa: F401  (registration)

    if name not in PROVIDERS:
        raise TTSError(f"unknown TTS provider {name!r}; available: {', '.join(sorted(PROVIDERS))}")
    return PROVIDERS[name](**kwargs)


def guard_cost(provider, characters):
    cost = provider.estimate_cost(characters)
    if provider.paid:
        if os.environ.get("BRIEF_ALLOW_PAID_TTS") != "1":
            raise TTSError(f"{provider.name} is a paid API (≈${cost:.2f} for {characters} chars). "
                           "Set BRIEF_ALLOW_PAID_TTS=1 after budget approval.")
        limit = float(os.environ.get("BRIEF_MAX_TTS_USD", "1.00"))
        if cost > limit:
            raise TTSError(f"estimated cost ${cost:.2f} exceeds BRIEF_MAX_TTS_USD=${limit:.2f}")
    return cost


__all__ = ["Provider", "TTSError", "chunk_text", "get", "guard_cost", "PROVIDERS", "register"]
