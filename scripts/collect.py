#!/usr/bin/env python3
"""Kept for compatibility: the collector now lives in the `brief` package."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from brief.__main__ import main  # noqa: E402

if __name__ == "__main__":
    main(["collect"])
