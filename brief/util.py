import datetime as dt
import hashlib
import json
import os
import pathlib
import tempfile
from zoneinfo import ZoneInfo

# BRIEF_ROOT lets tests run the whole pipeline in a temporary copy of the repo.
ROOT = pathlib.Path(os.environ.get("BRIEF_ROOT") or pathlib.Path(__file__).resolve().parents[1])
KYIV = ZoneInfo("Europe/Kyiv")


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def kyiv_date(ts: dt.datetime) -> str:
    return ts.astimezone(KYIV).date().isoformat()


def iso(ts):
    return ts.astimezone(dt.timezone.utc).isoformat(timespec="seconds") if ts else None


def from_iso(s):
    if not s:
        return None
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def load_json(path, default=None):
    path = pathlib.Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    """Atomic write: a crash mid-write never leaves a truncated file behind."""
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=path.suffix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def write_text(path, text):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-", suffix=path.suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def config(name):
    return load_json(ROOT / "config" / name)
