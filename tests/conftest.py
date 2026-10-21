import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = pathlib.Path(__file__).parent / "fixtures"
sys.path.insert(0, str(REPO))


def make_item(i, title, description="", source="Українська правда", source_id="pravda", published="2026-10-20T15:00:00+00:00",
              geography="national", region=None, url=None):
    from brief.normalize import item_id

    url = url or f"https://www.pravda.com.ua/news/test/{i}/"
    return {"id": item_id(url), "source_id": source_id, "source": source, "geography": geography,
            "source_region": region, "url": url, "title": title, "description": description,
            "published_at": published, "fetched_at": published, "categories": [], "date_issues": [],
            "status": "new"}


@pytest.fixture
def make():
    return make_item


@pytest.fixture
def editorial():
    from brief.util import config

    return config("editorial.json")


@pytest.fixture
def gazetteer():
    from brief.cluster import gazetteer_from_config
    from brief.util import config

    return gazetteer_from_config(config("regions.json"))


@pytest.fixture
def tmp_root(tmp_path):
    """A throwaway copy of the repo's config and sonic assets; the pipeline runs inside it."""
    for d in ("config", "audio"):
        shutil.copytree(REPO / d, tmp_path / d)
    (tmp_path / "data" / "raw").mkdir(parents=True)
    return tmp_path


def run_cli(root, *args, check=True, env_extra=None):
    env = {**os.environ, "BRIEF_ROOT": str(root), **(env_extra or {})}
    env.pop("BRIEF_ALLOW_PAID_TTS", None)
    r = subprocess.run([sys.executable, "-m", "brief", *args], cwd=REPO, env=env, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise AssertionError(f"brief {' '.join(args)} failed:\n{r.stdout}\n{r.stderr}")
    return r


@pytest.fixture
def cli():
    return run_cli


def write_pool(root, date, items):
    path = pathlib.Path(root) / "data" / "raw" / f"{date}.json"
    path.write_text(json.dumps({"date": date, "items": items}, ensure_ascii=False), encoding="utf-8")
    return path
