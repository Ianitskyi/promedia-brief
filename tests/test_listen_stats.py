"""Listening statistics (owner, 2026-11-17): start, half and end are reported once per edition."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_pages_load_the_listening_tracker():
    for page in ("index.html", "demo.html"):
        assert "/brief-listen.js" in (ROOT / page).read_text(encoding="utf-8")
    frame = (ROOT / "analytics-frame-v2.html").read_text(encoding="utf-8")
    for name in ("brief_play", "brief_progress", "brief_complete"):
        assert name in frame


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_start_half_and_end_are_reported_once():
    script = """
const vm=require('vm'),fs=require('fs');const sent=[];
const w={briefTrack:(n,p)=>sent.push([n,p.percent,p.brief_place,p.brief_edition])};w.window=w;
vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),w);
const u=w.briefListen('2026-11-16','brief_home');
u(0,0,false);u(0,74,true);u(10,74,true);u(40,74,true);u(50,74,true);u(72,74,true);u(74,74,false);u(74,74,true);
console.log(JSON.stringify(sent));
"""
    out = subprocess.run(["node", "-e", script, str(ROOT / "brief-listen.js")],
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == [
        ["brief_play", 0, "brief_home", "2026-11-16"],
        ["brief_progress", 50, "brief_home", "2026-11-16"],
        ["brief_complete", 100, "brief_home", "2026-11-16"],
    ]
