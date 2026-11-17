"""Live sync: GET /api/version goes up with every change to shared data, and only then."""

from fastapi.testclient import TestClient

from app.importer.run import run
from app.main import app
from app.models import Place
from tests.conftest import row
from tests.test_api import bob, client, db, login, places_by_name, review_by_url  # noqa: F401  (fixtures)
from tests.test_imports import NEW, post, token  # noqa: F401  (fixture)


def version(c) -> int:
    res = c.get("/api/version")
    assert res.status_code == 200
    assert res.headers["cache-control"] == "no-store"
    return res.json()["version"]


def test_version_needs_a_login(db):
    assert TestClient(app).get("/api/version").status_code == 401


def test_reading_and_logging_in_dont_move_it(client):
    v = version(client)
    client.get("/api/places")
    client.get("/api/stats")
    client.get("/api/reels/review")
    login("bob")  # a new login session is not shared data
    client.post("/api/auth/logout")
    assert version(login("alice")) == v


def test_every_kind_of_change_moves_it(client, bob):
    cafe = places_by_name(client)["Test Cafe"]
    steps = [
        lambda: client.post(f"/api/places/{cafe['id']}/visit", json={"visited": True}),
        lambda: client.post(f"/api/places/{cafe['id']}/visit", json={"notes": "get the cortado"}),
        lambda: client.put(f"/api/places/{cafe['id']}/tags", json={"tags": ["Seafood"]}),
        lambda: client.put(f"/api/places/{cafe['id']}/removed", json={"removed": True}),
        lambda: client.put(f"/api/places/{cafe['id']}/removed", json={"removed": False}),
        lambda: client.post("/api/places", json={"name": "Hand Added", "lat": 37.79, "lng": -122.4}),
        lambda: client.post(f"/api/reels/{review_by_url(client)['u4']['id']}/reject"),
    ]
    v = version(client)
    for i, step in enumerate(steps):
        assert step().status_code in (200, 201), i
        now = version(bob)  # the other person sees it move
        assert now > v, f"step {i} didn't move the version"
        v = now


def test_adding_a_spot_to_a_multi_spot_reel_moves_it(client):
    reel = review_by_url(client)["u5"]
    other = places_by_name(client)["Test Cafe"]
    v = version(client)
    res = client.post(f"/api/reels/{reel['id']}/place", json={"place_id": other["id"], "mode": "add"})
    assert res.status_code == 200
    assert version(client) > v


def test_a_change_that_changes_nothing_doesnt_move_it(client):
    cafe = places_by_name(client)["Test Cafe"]
    client.post(f"/api/places/{cafe['id']}/visit", json={"notes": "same"}).raise_for_status()
    v = version(client)
    client.post(f"/api/places/{cafe['id']}/visit", json={"notes": "same"}).raise_for_status()
    assert version(client) == v


def test_failed_requests_dont_move_it(client):
    v = version(client)
    assert client.post("/api/places", json={"name": "Far Away", "lat": 40.7, "lng": -74.0}).status_code == 422
    assert client.put("/api/places/999999/removed", json={"removed": True}).status_code == 404
    assert version(client) == v


def test_a_muse_upload_moves_it(client, token):
    v = version(client)
    assert post(NEW).status_code == 200
    assert version(client) > v


def test_a_command_line_import_moves_it(client, db, write_export):
    v = version(client)
    with db() as s:
        run([write_export([row(venue="Brand New Spot", post_url="cli-1", address="9 Elm St, Oakland, CA 94607")], "cli.json")], s)
    assert version(client) > v


def test_a_rolled_back_change_doesnt_move_it(client, db):
    v = version(client)
    with db() as s:
        s.get(Place, places_by_name(client)["Test Cafe"]["id"]).name = "Renamed"
        s.flush()  # the bump is written here, in the same transaction...
        s.rollback()  # ...so it goes away with the change
    assert version(client) == v
    assert "Test Cafe" in places_by_name(client)
