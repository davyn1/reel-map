import json

from app.backup import export_log, restore_log
from app.importer.run import run
from tests.conftest import row
from tests.test_api import client, db, login  # noqa: F401  (fixtures)
from tests.test_backup import fresh_session, place


def place_named(c, name):
    return next((p for p in c.get("/api/places").json() if p["name"] == name), None)


def test_removed_place_leaves_the_map_and_undo_brings_it_back(client):
    cafe = place_named(client, "Test Cafe")
    client.post(f"/api/places/{cafe['id']}/visit", json={"visited": True, "rating": 4, "notes": "go early"}).raise_for_status()
    assert client.get("/api/stats").json()["visited"] == 1

    res = client.put(f"/api/places/{cafe['id']}/removed", json={"removed": True})
    assert res.status_code == 200
    assert place_named(client, "Test Cafe") is None
    assert client.get("/api/stats").json()["visited"] == 0  # counts only places still on the map

    client.put(f"/api/places/{cafe['id']}/removed", json={"removed": False}).raise_for_status()
    back = place_named(client, "Test Cafe")
    assert back["id"] == cafe["id"] and back["rating"] == 4 and back["notes"] == "go early"
    assert client.get("/api/stats").json()["visited"] == 1


def test_a_later_export_does_not_bring_it_back(client, db, write_export):
    cafe = place_named(client, "Test Cafe")
    client.put(f"/api/places/{cafe['id']}/removed", json={"removed": True}).raise_for_status()
    with db() as s:  # the same reel arrives again, e.g. in Muse's next full export
        summary = run([write_export([row(venue="Test Cafe", post_url="u1")], name="reels-again.json")], s)
    assert summary.skipped == 1 and summary.imported == 0
    assert place_named(client, "Test Cafe") is None


def test_unknown_place(client):
    assert client.put("/api/places/9999/removed", json={"removed": True}).status_code == 404


def test_adding_a_removed_place_by_its_link_brings_it_back(client):
    made = client.post("/api/places", json={"name": "Corner Bakery", "lat": 37.8, "lng": -122.27,
                                            "link": "https://www.instagram.com/reel/BACK1/"}).json()
    client.put(f"/api/places/{made['id']}/removed", json={"removed": True}).raise_for_status()
    res = client.post("/api/places", json={"name": "Corner Bakery", "lat": 37.8, "lng": -122.27,
                                           "link": "https://www.instagram.com/reel/BACK1/"})
    assert res.status_code == 201 and res.json()["id"] == made["id"]
    assert place_named(client, "Corner Bakery") is not None


def test_a_removed_place_does_not_block_adding_one_nearby(client):
    cafe = place_named(client, "Test Cafe")
    client.put(f"/api/places/{cafe['id']}/removed", json={"removed": True}).raise_for_status()
    res = client.post("/api/places", json={"name": "Test Cafe", "lat": cafe["lat"], "lng": cafe["lng"]})
    assert res.status_code == 201 and res.json()["id"] != cafe["id"]


def test_removals_survive_a_backup_and_restore(write_export):
    a = fresh_session(write_export)
    place(a, "Tacko").removed = True
    a.commit()
    log = json.loads(json.dumps(export_log(a)))
    assert log["removed"] == [{"name": "Tacko", "post_urls": ["https://ig/u3"]}]

    b = fresh_session(write_export)  # a fresh database with the same exports imported
    restore_log(b, log)
    assert place(b, "Tacko").removed and not place(b, "Plain").removed
