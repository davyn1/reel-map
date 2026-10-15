import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_session, init_db
from app.importer.run import run
from app.main import app
from app.models import Place
from tests.conftest import row

OAKLAND_POPUP = dict(address="Oakland, CA, United States", city="Oakland", lat=37.805, lng=-122.273, confidence="low")


@pytest.fixture
def db(write_export):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as s:
        run([write_export([
            row(venue="Test Cafe", post_url="u1"),
            row(venue="Test Cafe", post_url="u2", posted_by="other"),
            row(venue="Its On The Flo", post_url="u3", **OAKLAND_POPUP),
            row(venue="", address="", lat=None, lng=None, confidence="none", post_url="u4"),
            row(venue="Deli Board (multi-spot reel)", address="1590 Bryant St, San Francisco, CA 94103",
                lat=37.767, lng=-122.411, note="reel covers 3 sandwich shops", post_url="u5"),
        ])], s)

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield Session
    app.dependency_overrides.clear()


@pytest.fixture
def client(db):
    return TestClient(app)


def places_by_name(client):
    return {p["name"]: p for p in client.get("/api/places").json()}


def review_by_url(client, **params):
    return {r["post_url"]: r for r in client.get("/api/reels/review", params=params).json()}


def test_list_places(client):
    places = places_by_name(client)
    assert set(places) == {"Test Cafe", "Its On The Flo", "Deli Board"}
    cafe = places["Test Cafe"]
    assert [r["post_url"] for r in cafe["reels"]] == ["u1", "u2"]
    assert cafe["visited"] is False and cafe["is_approximate"] is False
    assert cafe["google_maps_url"].startswith("https://www.google.com/maps/search/?api=1&query=Test+Cafe")
    assert places["Its On The Flo"]["is_approximate"] is True


def test_set_visited_and_unset(client):
    pid = places_by_name(client)["Test Cafe"]["id"]
    on = client.post(f"/api/places/{pid}/visit", json={"visited": True}).json()
    assert on["visited"] is True and on["visited_date"] is not None
    again = client.post(f"/api/places/{pid}/visit", json={"visited": True}).json()
    assert again["visited_date"] == on["visited_date"]  # idempotent, not a flip
    off = client.post(f"/api/places/{pid}/visit", json={"visited": False}).json()
    assert off["visited"] is False and off["visited_date"] is None
    assert places_by_name(client)["Test Cafe"]["visited"] is False


def test_visit_unknown_place_404(client):
    assert client.post("/api/places/999/visit", json={"visited": True}).status_code == 404


def test_review_queue_and_flag_filter(client):
    assert set(review_by_url(client)) == {"u4", "u5"}
    assert set(review_by_url(client, flag="no_venue")) == {"u4"}
    assert set(review_by_url(client, flag="multi_spot")) == {"u5"}
    assert client.get("/api/reels/review", params={"flag": "bogus"}).status_code == 422
    assert "no_venue" in client.get("/api/flags").json()


def test_attach_new_place_resolves_reel(client):
    reel = review_by_url(client)["u4"]
    out = client.post(f"/api/reels/{reel['id']}/place",
                      json={"new_place": {"name": "Found It", "lat": 37.79, "lng": -122.4, "address": "1 Market St"}}).json()
    assert out["status"] == "matched" and out["place"]["name"] == "Found It"
    assert "u4" not in review_by_url(client)
    assert places_by_name(client)["Found It"]["reels"][0]["post_url"] == "u4"


def test_attach_existing_place(client):
    reel = review_by_url(client)["u4"]
    pid = places_by_name(client)["Test Cafe"]["id"]
    out = client.post(f"/api/reels/{reel['id']}/place", json={"place_id": pid}).json()
    assert out["place"]["id"] == pid
    assert len(places_by_name(client)["Test Cafe"]["reels"]) == 3


def test_attach_rejects_bad_input(client):
    rid = review_by_url(client)["u4"]["id"]
    assert client.post(f"/api/reels/{rid}/place", json={}).status_code == 422
    swapped = {"new_place": {"name": "X", "lat": -122.4, "lng": 37.79}}
    assert client.post(f"/api/reels/{rid}/place", json=swapped).status_code == 422
    assert client.post(f"/api/reels/{rid}/place", json={"place_id": 999}).status_code == 404
    assert client.post(f"/api/reels/{rid}/place", json={"place_id": 1, "mode": "add"}).status_code == 409


def test_multi_spot_add_spots_then_resolve(client):
    rid = review_by_url(client)["u5"]["id"]
    for name, lat in [("Lou's Cafe", 37.78), ("Ike's", 37.76)]:
        out = client.post(f"/api/reels/{rid}/place",
                          json={"mode": "add", "new_place": {"name": name, "lat": lat, "lng": -122.42}}).json()
        assert out["status"] == "needs_review"
    assert [p["name"] for p in out["extra_places"]] == ["Lou's Cafe", "Ike's"]
    places = places_by_name(client)
    assert all(places[n]["reels"][0]["post_url"] == "u5" for n in ("Deli Board", "Lou's Cafe", "Ike's"))
    assert client.post(f"/api/reels/{rid}/resolve").json()["status"] == "matched"
    assert review_by_url(client) == {"u4": review_by_url(client)["u4"]}


def test_resolve_without_place_409(client):
    assert client.post(f"/api/reels/{review_by_url(client)['u4']['id']}/resolve").status_code == 409


def test_reject_removes_orphaned_place_but_keeps_visited_ones(client, db):
    rid = review_by_url(client)["u5"]["id"]
    out = client.post(f"/api/reels/{rid}/reject").json()
    assert out["status"] == "rejected" and out["place"] is None
    assert "Deli Board" not in places_by_name(client)
    assert "u5" not in review_by_url(client)

    # A place you've been to survives losing its last reel.
    with db() as s:
        flo = s.scalars(select(Place).where(Place.name == "Its On The Flo")).one()
        flo_reel_id = flo.reels[0].id
    client.post(f"/api/places/{flo.id}/visit", json={"visited": True})
    client.post(f"/api/reels/{flo_reel_id}/reject")
    assert places_by_name(client)["Its On The Flo"]["reels"] == []


def test_replace_moves_reel_and_cleans_up_old_place(client):
    places = places_by_name(client)
    rid = places["Its On The Flo"]["reels"][0]["id"]
    client.post(f"/api/reels/{rid}/place", json={"place_id": places["Test Cafe"]["id"]})
    assert "Its On The Flo" not in places_by_name(client)


def test_places_have_city_and_import_order(client):
    places = client.get("/api/places").json()
    assert [p["name"] for p in places] == ["Test Cafe", "Its On The Flo", "Deli Board"]
    assert places[0]["city"] == "Oakland"


def test_place_city_falls_back_to_address():
    from app.models import Place
    from app.routers.places import place_city
    assert place_city(Place(name="X", lat=0, lng=0, address="1 Market St, San Francisco, CA 94105")) == "San Francisco"
    assert place_city(Place(name="X", lat=0, lng=0, address=None)) is None


def test_stats(client):
    assert client.get("/api/stats").json() == {"reels_saved": 5, "on_map": 3, "cities": 1, "needs_review": 2}
    client.post(f"/api/reels/{review_by_url(client)['u4']['id']}/reject")
    assert client.get("/api/stats").json() == {"reels_saved": 4, "on_map": 3, "cities": 1, "needs_review": 1}
