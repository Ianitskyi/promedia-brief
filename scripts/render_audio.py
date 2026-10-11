#!/usr/bin/env python3
import os, re, subprocess, tempfile
from pathlib import Path
from google.cloud import texttospeech

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path(os.environ.get("BRIEF_SCRIPT", ROOT / "scripts" / "2026-10-03.md"))
OUT = Path(os.environ.get("BRIEF_OUTPUT", ROOT / "audio" / "daily.mp3"))

FEMALE = os.environ.get("BRIEF_FEMALE_VOICE", "uk-UA-Chirp3-HD-Kore")
MALE = os.environ.get("BRIEF_MALE_VOICE", "uk-UA-Chirp3-HD-Orus")
RATE = float(os.environ.get("BRIEF_SPEAKING_RATE", "1.08"))

text = SCRIPT.read_text(encoding="utf-8")

def extract_sections(src: str):
    src = re.sub(r"^#.*?$", "", src, flags=re.M)
    src = re.sub(r"^##.*?$", "", src, flags=re.M)
    src = src.replace("[INTRO — instrumental sonic logo, 2.5–4 sec]", "")
    parts = src.split("[BUMPER — instrumental, ~1.2 sec]")
    if len(parts) != 2:
        raise RuntimeError("Could not find BUMPER marker in script")
    national = parts[0].strip()
    regional = parts[1].split("[OUTRO — instrumental, 3–4 sec]")[0].strip()
    return national, regional

def chunk_text(s: str, limit=3600):
    paras = [p.strip() for p in s.split("\n\n") if p.strip()]
    chunks, cur = [], ""
    for p in paras:
        candidate = (cur + "\n\n" + p).strip() if cur else p
        if len(candidate.encode("utf-8")) <= limit:
            cur = candidate
        else:
            if cur: chunks.append(cur)
            cur = p
    if cur: chunks.append(cur)
    return chunks

client = texttospeech.TextToSpeechClient()

def synthesize_block(text: str, voice_name: str, out_path: Path):
    tmpdir = Path(tempfile.mkdtemp())
    parts = []
    for i, chunk in enumerate(chunk_text(text)):
        resp = client.synthesize_speech(
            request={
                "input": texttospeech.SynthesisInput(text=chunk),
                "voice": texttospeech.VoiceSelectionParams(
                    language_code="uk-UA",
                    name=voice_name,
                ),
                "audio_config": texttospeech.AudioConfig(
                    audio_encoding=texttospeech.AudioEncoding.MP3,
                    speaking_rate=RATE,
                ),
            }
        )
        p = tmpdir / f"part-{i:03d}.mp3"
        p.write_bytes(resp.audio_content)
        parts.append(p)

    concat = tmpdir / "concat.txt"
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in parts), encoding="utf-8")
    subprocess.run([
        "ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),
        "-c:a","libmp3lame","-b:a","128k",str(out_path)
    ], check=True)

national, regional = extract_sections(text)

OUT.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    nat = td / "national.mp3"
    reg = td / "regional.mp3"
    synthesize_block(national, FEMALE, nat)
    synthesize_block(regional, MALE, reg)

    concat = td / "master.txt"
    items = [
        ROOT / "audio" / "intro.mp3",
        nat,
        ROOT / "audio" / "bumper.mp3",
        reg,
        ROOT / "audio" / "outro.mp3",
    ]
    concat.write_text("\n".join(f"file '{p.as_posix()}'" for p in items), encoding="utf-8")

    subprocess.run([
        "ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),
        "-c:a","libmp3lame","-b:a","160k",str(OUT)
    ], check=True)

print(OUT)
