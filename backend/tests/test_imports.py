import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import row
from tests.test_api import bob, client, db, login  # noqa: F401  (fixtures)

TOKEN = "test-upload-token-0123456789"
NEW = [
    row(venue="Brand New Spot", address="9 New St, Oakland, CA 94607", post_url="https://www.instagram.com/reel/NEW1/"),
    row(venue="Another One", address="10 New St, Oakland, CA 94607", post_url="https://www.instagram.com/p/NEW2/?igsh=xyz"),
]


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setenv("FOOD_MAP_IMPORT_TOKEN", TOKEN)
    return TOKEN


def post(body, token: str | None = TOKEN, c: TestClient | None = None):
    c = c or TestClient(app)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    data = body if isinstance(body, (bytes, str)) else json.dumps(body)
    return c.post("/api/import", content=data, headers=headers)


def test_upload_needs_the_token_or_a_login(db, token):
    assert post(NEW, token=None).status_code == 401
    assert post(NEW, token="wrong").status_code == 401


def test_token_uploads_are_off_until_configured(db, monkeypatch):
    monkeypatch.delenv("FOOD_MAP_IMPORT_TOKEN", raising=False)
    res = post(NEW, token="anything")
    assert res.status_code == 503 and "aren't set up" in res.json()["detail"]


def test_upload_imports_saves_the_file_and_skips_known_reels(db, token, client, uploads_in_tmp):
    res = post(NEW)
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["imported"], body["pinned"], body["skipped"]) == (2, 2, 0)
    saved = uploads_in_tmp / body["saved_as"]
    assert saved.is_file() and json.loads(saved.read_text(encoding="utf-8"))[0]["venue"] == "Brand New Spot"
    names = {p["name"] for p in client.get("/api/places").json()}
    assert {"Brand New Spot", "Another One"} <= names

    again = post(NEW).json()  # Muse sends the full export every day
    assert (again["imported"], again["skipped"]) == (0, 2)


def test_upload_normalizes_reel_links(db, token, client):
    post(NEW)
    urls = {r["post_url"] for p in client.get("/api/places").json() for r in p["reels"]}
    assert "https://www.instagram.com/reel/NEW2/" in urls  # was /p/NEW2/?igsh=xyz
    # the same reel written differently next time is recognized, not duplicated
    res = post([row(venue="Another One", post_url="https://instagram.com/reel/NEW2")]).json()
    assert (res["imported"], res["skipped"]) == (0, 1)


def test_wrapped_reels_object_is_accepted(db, token):
    res = post({"reels": NEW})
    assert res.status_code == 200 and res.json()["imported"] == 2


def test_broken_json_is_kept_and_reported(db, token, client, uploads_in_tmp):
    res = post('[\n {"venue": "A",}\n]')
    assert res.status_code == 400
    assert "line 2, column 16" in res.json()["detail"]
    assert len(list(uploads_in_tmp.glob("*.invalid"))) == 1 and not list(uploads_in_tmp.glob("*.json"))
    last = client.get("/api/imports").json()[0]
    assert last["ok"] is False and "line 2" in last["error"]


def test_empty_and_oversized_uploads(db, token, monkeypatch):
    from app.routers import imports

    assert post(b"   ").status_code == 400
    monkeypatch.setattr(imports, "MAX_UPLOAD_BYTES", 100)
    assert post(NEW).status_code == 413


def test_logged_in_person_can_upload(db, client):
    res = post(NEW, token=None, c=client)
    assert res.status_code == 200 and res.json()["imported"] == 2
    assert client.get("/api/imports").json()[0]["filename"].endswith("(from alice)")


def test_recent_imports_needs_login_and_lists_newest_first(db, token, client):
    assert TestClient(app).get("/api/imports").status_code == 401
    post(NEW)
    post(NEW)
    runs = client.get("/api/imports").json()
    assert [r["imported"] for r in runs[:2]] == [0, 2]
    assert runs[0]["source"] == "upload" and runs[0]["filename"].endswith("(from muse)")


def test_two_uploads_in_the_same_second_keep_both_files(db, token, uploads_in_tmp):
    post(NEW)
    post(NEW)
    assert len(list(uploads_in_tmp.glob("reels-upload-*.json"))) == 2
