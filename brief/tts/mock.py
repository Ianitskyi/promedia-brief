"""Offline placeholder: silence + a faint tone, length proportional to the text.

Used by tests and dry runs. Mock audio can never be published (publish.py refuses it).
"""
import os
import subprocess

from . import register
from .base import Provider, TTSError

CHARS_PER_SECOND = 15.0


@register
class MockProvider(Provider):
    name = "mock"
    paid = False
    max_chars = 1500
    output_ext = "wav"
    default_voice = "placeholder"

    calls = 0

    def synthesize(self, text, out_path):
        # BRIEF_MOCK_FAIL_AFTER=n simulates a provider outage after n calls (tests of resume-after-failure)
        fail_after = os.environ.get("BRIEF_MOCK_FAIL_AFTER")
        if fail_after is not None and MockProvider.calls >= int(fail_after):
            raise TTSError("mock: simulated outage")
        MockProvider.calls += 1
        seconds = max(0.4, len(text) / CHARS_PER_SECOND)
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
             f"sine=frequency=330:sample_rate=24000:duration={seconds:.2f}",
             "-af", "volume=0.05", "-ac", "1", "-f", "wav", str(out_path)],
            check=True,
        )
        return out_path
