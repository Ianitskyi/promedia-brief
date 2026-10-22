import os


class TTSError(RuntimeError):
    pass


class Provider:
    name = "base"
    paid = True
    # USD per 1M characters, from the provider's public price list (see docs/TTS.md).
    price_per_million = 0.0
    free_chars_per_month = 0
    max_chars = 4000
    measure_bytes = False  # some APIs limit UTF-8 bytes, not characters
    output_ext = "mp3"
    # text transforms needed by this engine (e.g. Piper reads only lowercase, no digits)
    spell_digits = False
    lowercase = False
    transliterate_latin = False
    stress_marks = False  # engine reads U+0301 after a vowel as a stress mark (config/stress.json)

    def __init__(self, voice=None, **options):
        self.voice = voice or self.default_voice
        self.options = options

    default_voice = None

    def estimate_cost(self, characters):
        return characters * self.price_per_million / 1_000_000

    def env(self, key):
        v = os.environ.get(key)
        if not v:
            raise TTSError(f"{self.name}: environment variable {key} is not set")
        return v

    def synthesize(self, text, out_path):
        """Write audio for exactly `text` to out_path. Must raise on any failure."""
        raise NotImplementedError

    def describe(self):
        return {"provider": self.name, "voice": self.voice, "paid": self.paid,
                "price_per_million_chars_usd": self.price_per_million}
