import json
import os

# Tests talk plain http to the test client; secure cookies would never be sent back.
os.environ["FOOD_MAP_COOKIE_SECURE"] = "false"
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import init_db

REAL_EXPORT = Path(__file__).resolve().parents[2] / "data" / "reels.json"


@pytest.fixture(autouse=True)
def log_in_tmp(tmp_path, monkeypatch):
    """Never let tests write the real personal/my-log.json."""
    from app import backup

    path = tmp_path / "personal" / "my-log.json"
    monkeypatch.setattr(backup, "LOG_PATH", path)
    return path


@pytest.fixture(autouse=True)
def uploads_in_tmp(tmp_path, monkeypatch):
    """Never let tests write uploaded exports into the real data/ folder."""
    from app.routers import imports

    folder = tmp_path / "uploads"
    monkeypatch.setattr(imports, "DATA_DIR", folder)
    return folder


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    init_db(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        yield s


@pytest.fixture
def write_export(tmp_path):
    def _write(rows, name="reels.json"):
        path = tmp_path / name
        path.write_text(rows if isinstance(rows, str) else json.dumps(rows), encoding="utf-8")
        return path

    return _write


def row(**overrides):
    base = {
        "venue": "Test Cafe",
        "address": "1 Main St, Oakland, CA 94607, United States",
        "city": "Oakland",
        "lat": 37.8,
        "lng": -122.27,
        "post_url": "https://www.instagram.com/reel/A1/",
        "posted_by": "someone",
        "dish": "a dish",
        "confidence": "high",
        "note": "",
    }
    base.update(overrides)
    return base
