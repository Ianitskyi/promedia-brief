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


def to_wav(src, dst):
    """Decode any input to a uniform mono PCM wav so parts can be concatenated safely."""
    _run(["-i", str(src), "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le", str(dst)])
    return dst


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
    """parts: list of ("file", path) | ("pause", ms). Returns duration of the result."""
    workdir = pathlib.Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    wavs = []
    for i, (kind, value) in enumerate(parts):
        out = workdir / f"part-{i:04d}.wav"
        if kind == "pause":
            silence(out, value)
        elif kind == "file":
            to_wav(value, out)
        else:
            raise AudioError(f"unknown part kind {kind}")
        wavs.append(out)
    joined = concat(wavs, workdir / "joined.wav")
    master(joined, dst_mp3)
    return duration(dst_mp3)
