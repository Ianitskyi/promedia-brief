#!/usr/bin/env python3
"""Conservative non-destructive pause normalization for BRIEF demo audio.

Usage:
    python scripts/normalize_demo_pauses.py input.mp3 output.mp3
Requires ffmpeg and pydub. The voice samples are unchanged; only the middle of
silence segments longer than min-pause-ms is removed. Preview before publication.
"""
import argparse
from pydub import AudioSegment, silence

def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("output")
    p.add_argument("--threshold", type=float, default=-38,
                   help="Silence threshold in dBFS")
    p.add_argument("--min-pause-ms", type=int, default=1100)
    p.add_argument("--target-ms", type=int, default=720)
    args = p.parse_args()

    recording = AudioSegment.from_file(args.input)
    intervals = silence.detect_silence(
        recording, min_silence_len=args.min_pause_ms,
        silence_thresh=args.threshold, seek_step=5
    )
    normalized = AudioSegment.empty()
    previous_end = 0
    for i, (start, end) in enumerate(intervals):
        duration = end - start
        retained = min(duration, args.target_ms + (i % 3) * 45)
        to_remove = duration - retained
        cut_start = start + to_remove // 2
        cut_end = end - (to_remove - to_remove // 2)
        normalized += recording[previous_end:cut_start]
        previous_end = cut_end
    normalized += recording[previous_end:]
    normalized.export(args.output, format="mp3", bitrate="128k")
    print(f"Adjusted {len(intervals)} long pauses; "
          f"{len(recording)/1000:.2f}s -> {len(normalized)/1000:.2f}s")

if __name__ == "__main__":
    main()
