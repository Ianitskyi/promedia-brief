"""Audio assembly with ffmpeg: pauses, concatenation, loudness normalisation."""
import json
import pathlib
import subprocess

SAMPLE_RATE = 44100
TARGET_LUFS = -16.0  # common spoken-word/podcast target; true peak -1.5 dBTP
TRUE_PEAK = -1.5
BITRATE = "64k"      # mono speech


class AudioError(RuntimeError):
    pass


def _run(args):
    r = subprocess.run(["ffmpeg", "-v", "error", "-y", *args], capture_output=True)
    if r.returncode != 0:
        raise AudioError(r.stderr.decode("utf-8", "replace")[-500:])


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                       capture_output=True)
    if r.returncode != 0:
        raise AudioError(f"ffprobe failed for {path}")
    return float(json.loads(r.stdout)["format"]["duration"])


# Silence the voice adds before and after a sentence (ElevenLabs: up to ~1 s each side). Owner, 18.11.2026:
# a story must sound as one block — a long gap inside it sounded like the story had ended. Each sentence
# is trimmed to its speech (keeping TRIM_KEEP_S), so the only pauses are the ones render.py sets.
TRIM_THRESHOLD_DB = -45
TRIM_KEEP_S = 0.04
_TRIM_EDGE = (f"silenceremove=start_periods=1:start_duration=0:start_threshold={TRIM_THRESHOLD_DB}dB"
              f":start_silence={TRIM_KEEP_S}")
TRIM = ",".join([_TRIM_EDGE, "areverse", _TRIM_EDGE, "areverse"])


def to_wav(src, dst, af=None, trim=False):
    """Decode any input to a uniform mono PCM wav so parts can be concatenated safely.
    af: optional ffmpeg audio filter (tempo/pitch adjustment of a voice);
    trim: cut the silence at the start and end of a synthesized sentence."""
    filters = ",".join(x for x in (TRIM if trim else None, af) if x)
    _run(["-i", str(src), *(["-af", filters] if filters else []), "-ac", "1", "-ar", str(SAMPLE_RATE),
          "-c:a", "pcm_s16le", str(dst)])
    if trim and pathlib.Path(dst).stat().st_size < SAMPLE_RATE * 2 * 0.05:  # nothing above the threshold
        return to_wav(src, dst, af)  # a very quiet clip stays whole rather than vanish
    return dst


def voice_filter(tempo=1.0, semitones=0.0):
    """ffmpeg filter that speeds speech up by `tempo` and shifts its pitch by `semitones`
    (negative = lower) without changing the speed. None when nothing changes."""
    if abs(tempo - 1) < 1e-3 and abs(semitones) < 1e-3:
        return None
    ratio = 2 ** (semitones / 12)
    filters = []
    if abs(semitones) >= 1e-3:  # resample to shift pitch, then undo the speed change
        filters += [f"asetrate={SAMPLE_RATE}*{ratio:.6f}", f"aresample={SAMPLE_RATE}"]
    speed = tempo / ratio if abs(semitones) >= 1e-3 else tempo
    while speed > 2.0:
        filters.append("atempo=2.0")
        speed /= 2.0
    while speed < 0.5:
        filters.append("atempo=0.5")
        speed /= 0.5
    filters.append(f"atempo={speed:.6f}")
    return ",".join(filters)


def silence(dst, ms):
    _run(["-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono", "-t", f"{ms / 1000:.3f}",
          "-c:a", "pcm_s16le", str(dst)])
    return dst


def concat(parts, dst_wav):
    """Concatenate uniform wavs in order."""
    if not parts:
        raise AudioError("nothing to concatenate")
    lst = pathlib.Path(dst_wav).with_suffix(".txt")
    lst.write_text("".join(f"file '{pathlib.Path(p).resolve().as_posix()}'\n" for p in parts), encoding="utf-8")
    _run(["-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(dst_wav)])
    lst.unlink()
    return dst_wav


def master(src_wav, dst_mp3, normalize=True):
    """Loudness-normalise (EBU R128) and encode to mono mp3."""
    af = [f"loudnorm=I={TARGET_LUFS}:TP={TRUE_PEAK}:LRA=11"] if normalize else []
    args = ["-i", str(src_wav)]
    if af:
        args += ["-af", ",".join(af)]
    args += ["-ar", str(SAMPLE_RATE), "-ac", "1", "-c:a", "libmp3lame", "-b:a", BITRATE, str(dst_mp3)]
    _run(args)
    return dst_mp3


def assemble(parts, dst_mp3, workdir):
    """parts: list of ("file", path[, ffmpeg filter]) | ("speech", path[, filter]) | ("pause", ms).
    "speech" is a synthesized sentence: its own leading/trailing silence is cut. Returns the duration."""
    workdir = pathlib.Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    wavs = []
    for i, part in enumerate(parts):
        kind, value = part[0], part[1]
        out = workdir / f"part-{i:04d}.wav"
        if kind == "pause":
            silence(out, value)
        elif kind in ("file", "speech"):
            to_wav(value, out, part[2] if len(part) > 2 else None, trim=kind == "speech")
        else:
            raise AudioError(f"unknown part kind {kind}")
        wavs.append(out)
    joined = concat(wavs, workdir / "joined.wav")
    master(joined, dst_mp3)
    return duration(dst_mp3)
