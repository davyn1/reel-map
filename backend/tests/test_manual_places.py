import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backup import export_log, restore_log
from app.db import init_db
from app.importer.run import run
from tests.conftest import row
from tests.test_api import bob, client, db, places_by_name  # noqa: F401  (fixtures)

SPOT = {"name": "Corner Taqueria", "lat": 37.79, "lng": -122.40, "address": "1 Mission St, San Francisco, CA 94105"}


def add(c, **overrides):
    return c.post("/api/places", json={**SPOT, **overrides})


def test_add_a_place_by_hand(client, bob):
    res = add(client, favorite=True, notes="try the al pastor", tags=["Mexican"])
    assert res.status_code == 201, res.text
    place = res.json()
    assert (place["name"], place["favorite"], place["notes"], place["tags"]) == ("Corner Taqueria", True, "try the al pastor", ["Mexican"])
    assert place["reels"][0]["added_by"] == "Alice" and place["reels"][0]["post_url"].startswith("manual:")
    # the friend sees it, with Alice's log
    theirs = places_by_name(bob)["Corner Taqueria"]
    assert theirs["others"][0]["display_name"] == "Alice" and theirs["favorite"] is False


def test_tags_are_automatic_unless_picked(client):
    place = add(client, name="Mission Pizza House").json()
    assert place["tags"] == ["Pizza & Italian"] and place["tags_edited"] is False


def test_visited_on_add_stamps_today(client):
    from datetime import date

    place = add(client, visited=True).json()
    assert place["visited"] is True and place["visited_date"] == date.today().isoformat()


def test_instagram_link_is_normalized_and_recognized_later(client, uploads_in_tmp, monkeypatch):
    place = add(client, link="https://www.instagram.com/p/HANDADD1/?igsh=abc").json()
    assert place["reels"][0]["post_url"] == "https://www.instagram.com/reel/HANDADD1/"
    # Muse later exports the same reel: skipped, not duplicated
    monkeypatch.setenv("FOOD_MAP_IMPORT_TOKEN", "t" * 30)
    res = client.post("/api/import", json=[row(venue="Corner Taqueria", post_url="https://instagram.com/reel/HANDADD1")],
                      headers={"Authorization": "Bearer " + "t" * 30})
    assert (res.json()["imported"], res.json()["skipped"]) == (0, 1)


def test_same_link_twice_is_refused(client):
    add(client, link="https://example.com/taqueria")
    res = add(client, name="Something Else", lat=37.70, link="https://example.com/taqueria")
    assert res.status_code == 409
    assert res.json()["detail"]["kind"] == "same_link" and "Corner Taqueria" in res.json()["detail"]["message"]


def test_similar_place_nearby_asks_first(client):
    add(client)
    res = add(client, name="Corner Taqueria SF", lat=37.7901)  # ~11 m away
    assert res.status_code == 409 and res.json()["detail"]["kind"] == "similar_nearby"
    assert add(client, name="Corner Taqueria SF", lat=37.7901, force=True).status_code == 201
    # a different name at the same spot is fine (food halls)
    assert add(client, name="Ramen Stall", lat=37.7901).status_code == 201


def test_bad_input(client):
    assert add(client, lat=-122.40, lng=37.79).status_code == 422  # swapped
    assert add(client, name="   ").status_code == 422
    assert add(client, link="instagram.com/reel/x").status_code == 422
    assert add(client, tags=["Sandwiches"]).status_code == 422


def test_needs_login(db):
    from fastapi.testclient import TestClient

    from app.main import app

    assert TestClient(app).post("/api/places", json=SPOT).status_code == 401


def test_hand_added_places_survive_a_rebuild(client, db, write_export):
    add(client, favorite=True, link="https://www.instagram.com/reel/HANDADD2/")
    with db() as s:
        log = json.loads(json.dumps(export_log(s)))
    assert log["manual_places"][0]["name"] == "Corner Taqueria" and log["manual_places"][0]["added_by"] == "alice"

    # a fresh database rebuilt from the Muse export alone doesn't have it...
    engine = create_engine("sqlite://")
    init_db(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as fresh:
        run([write_export([row(post_url="u1")])], fresh)
        restored, unmatched = restore_log(fresh, log)
        assert unmatched == []
        out = export_log(fresh)
        assert out["manual_places"] == log["manual_places"]
        assert out["users"]["alice"]["places"][0]["name"] == "Corner Taqueria"
