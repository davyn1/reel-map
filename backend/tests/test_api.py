import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_session, init_db
from app.importer.run import run
from app.main import app
from app.models import Place
from app.users import add_user
from tests.conftest import row

PASSWORDS = {"alice": "alice-password", "bob": "bob-password"}

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
        add_user(s, "alice", "Alice", PASSWORDS["alice"])  # first account
        add_user(s, "bob", "Bob", PASSWORDS["bob"])

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield Session
    app.dependency_overrides.clear()


def login(username: str) -> TestClient:
    c = TestClient(app)
    res = c.post("/api/auth/login", json={"username": username, "password": PASSWORDS[username]})
    assert res.status_code == 200, res.text
    return c


@pytest.fixture
def client(db):
    """Logged in as alice."""
    return login("alice")


@pytest.fixture
def bob(db):
    return login("bob")


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
    assert client.get("/api/stats").json() == {"reels_saved": 5, "on_map": 3, "cities": 1, "needs_review": 2, "visited": 0, "favorites": 0}
    client.post(f"/api/reels/{review_by_url(client)['u4']['id']}/reject")
    assert client.get("/api/stats").json() == {"reels_saved": 4, "on_map": 3, "cities": 1, "needs_review": 1, "visited": 0, "favorites": 0}


def visit(client, pid, **body):
    return client.post(f"/api/places/{pid}/visit", json=body)


def test_visit_log_partial_updates(client):
    pid = places_by_name(client)["Test Cafe"]["id"]
    out = visit(client, pid, visited=True, rating=4, notes="  get the wings  ").json()
    assert (out["visited"], out["rating"], out["notes"]) == (True, 4, "get the wings")
    # only the field sent changes
    out = visit(client, pid, rating=5).json()
    assert (out["rating"], out["notes"], out["visited"]) == (5, "get the wings", True)
    out = visit(client, pid, visited_date="2026-09-01").json()
    assert out["visited_date"] == "2026-09-01"
    out = visit(client, pid, notes=None).json()
    assert out["notes"] is None and out["rating"] == 5


def test_unvisiting_clears_date_and_rating_but_keeps_notes_and_favorite(client):
    pid = places_by_name(client)["Test Cafe"]["id"]
    visit(client, pid, visited=True, rating=3, notes="ok", favorite=True)
    out = visit(client, pid, visited=False).json()
    assert (out["visited"], out["visited_date"], out["rating"]) == (False, None, None)
    assert (out["notes"], out["favorite"]) == ("ok", True)


def test_rating_must_be_1_to_5(client):
    pid = places_by_name(client)["Test Cafe"]["id"]
    assert visit(client, pid, rating=6).status_code == 422
    assert visit(client, pid, rating=0).status_code == 422


def test_favorite_and_stats(client):
    pid = places_by_name(client)["Test Cafe"]["id"]
    assert visit(client, pid, favorite=True).json()["favorite"] is True
    visit(client, places_by_name(client)["Deli Board"]["id"], visited=True)
    stats = client.get("/api/stats").json()
    assert (stats["favorites"], stats["visited"]) == (1, 1)


def test_favorite_place_survives_losing_its_last_reel(client):
    places = places_by_name(client)
    visit(client, places["Deli Board"]["id"], favorite=True)
    client.post(f"/api/reels/{places['Deli Board']['reels'][0]['id']}/reject")
    assert "Deli Board" in places_by_name(client)


def test_places_have_tags(client):
    assert places_by_name(client)["Deli Board"]["tags"] == ["American"]


def test_edit_tags_then_reset(client):
    pid = places_by_name(client)["Deli Board"]["id"]
    assert client.get("/api/tags").json()[0] == "Mexican"
    out = client.put(f"/api/places/{pid}/tags", json={"tags": ["Seafood", "American", "American"]}).json()
    assert (out["tags"], out["tags_edited"]) == (["American", "Seafood"], True)  # deduped, display order
    assert places_by_name(client)["Deli Board"]["tags"] == ["American", "Seafood"]
    out = client.put(f"/api/places/{pid}/tags", json={"tags": []}).json()
    assert (out["tags"], out["tags_edited"]) == ([], True)
    out = client.put(f"/api/places/{pid}/tags", json={"tags": None}).json()
    assert (out["tags"], out["tags_edited"]) == (["American"], False)


def test_edit_tags_rejects_unknown_tags(client):
    pid = places_by_name(client)["Deli Board"]["id"]
    res = client.put(f"/api/places/{pid}/tags", json={"tags": ["Sandwiches"]})
    assert res.status_code == 422 and "Sandwiches" in res.json()["detail"]
    assert client.put("/api/places/999/tags", json={"tags": []}).status_code == 404


def test_api_changes_update_the_log(client, log_in_tmp):
    pid = next(p["id"] for p in client.get("/api/places").json() if p["name"] == "Test Cafe")
    client.post(f"/api/places/{pid}/visit", json={"visited": True, "rating": 4})
    entry = json.loads(log_in_tmp.read_text(encoding="utf-8"))["users"]["alice"]["places"][0]
    assert (entry["name"], entry["rating"]) == ("Test Cafe", 4)
    client.put(f"/api/places/{pid}/tags", json={"tags": ["Thai"]})
    assert json.loads(log_in_tmp.read_text(encoding="utf-8"))["tags"][0]["tags"] == ["Thai"]


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}


def test_built_frontend_is_served_but_api_wins(tmp_path):
    from fastapi import FastAPI

    from app.main import mount_frontend

    app = FastAPI()

    @app.get("/api/ping")
    def ping():
        return {"pong": True}

    assert mount_frontend(app, tmp_path) is False  # nothing built: nothing mounted
    (tmp_path / "index.html").write_text("<title>Food Map</title>", encoding="utf-8")
    (tmp_path / "app.js").write_text("console.log(1)", encoding="utf-8")
    assert mount_frontend(app, tmp_path) is True
    c = TestClient(app)
    assert "Food Map" in c.get("/").text
    assert c.get("/app.js").text == "console.log(1)"
    assert c.get("/api/ping").json() == {"pong": True}



# ---- logins -------------------------------------------------------------------------------

def test_everything_but_health_and_login_needs_a_login(db):
    anon = TestClient(app)
    assert anon.get("/api/health").status_code == 200
    for method, path in [("get", "/api/places"), ("get", "/api/stats"), ("get", "/api/tags"), ("get", "/api/flags"),
                         ("get", "/api/reels/review"), ("post", "/api/places/1/visit"), ("put", "/api/places/1/tags"),
                         ("post", "/api/reels/1/reject"), ("get", "/api/auth/me")]:
        res = anon.get(path) if method == "get" else getattr(anon, method)(path, json={})
        assert res.status_code == 401, path


def test_login_me_logout(db):
    c = login("alice")
    assert c.get("/api/auth/me").json() == {"username": "alice", "display_name": "Alice"}
    cookie = c.cookies.get("yums_session")
    assert cookie and len(cookie) > 30
    assert c.post("/api/auth/logout").status_code == 204
    assert c.get("/api/places").status_code == 401
    # the old token is gone server-side too, not just the cookie
    replay = TestClient(app, cookies={"yums_session": cookie})
    assert replay.get("/api/places").status_code == 401


def test_login_is_case_insensitive_on_username(db):
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"username": " Alice ", "password": PASSWORDS["alice"]}).status_code == 200


def test_wrong_password_and_lockout(db, monkeypatch):
    from app import auth

    monkeypatch.setattr(auth, "throttle", auth.LoginThrottle(max_failures=3, lockout_seconds=60))
    import app.routers.auth as auth_router

    monkeypatch.setattr(auth_router, "throttle", auth.throttle)
    c = TestClient(app)
    for _ in range(3):
        assert c.post("/api/auth/login", json={"username": "alice", "password": "nope-nope"}).status_code == 401
    # locked now, even with the right password
    res = c.post("/api/auth/login", json={"username": "alice", "password": PASSWORDS["alice"]})
    assert res.status_code == 429 and "Try again" in res.json()["detail"]
    # other accounts unaffected
    assert c.post("/api/auth/login", json={"username": "bob", "password": PASSWORDS["bob"]}).status_code == 200


def test_unknown_user_gets_the_same_error(db):
    c = TestClient(app)
    res = c.post("/api/auth/login", json={"username": "mallory", "password": "whatever-123"})
    assert res.status_code == 401 and res.json()["detail"] == "Wrong username or password."


# ---- friend mode --------------------------------------------------------------------------

def test_visits_are_per_person_and_visible_to_the_other(client, bob):
    pid = places_by_name(client)["Test Cafe"]["id"]
    client.post(f"/api/places/{pid}/visit", json={"visited": True, "rating": 5, "notes": "wings!"})
    bob.post(f"/api/places/{pid}/visit", json={"favorite": True})

    mine = places_by_name(client)["Test Cafe"]
    assert (mine["visited"], mine["rating"], mine["favorite"]) == (True, 5, False)
    assert mine["others"] == [{"username": "bob", "display_name": "Bob", "visited": False, "rating": None,
                               "notes": None, "favorite": True}]

    theirs = places_by_name(bob)["Test Cafe"]
    assert (theirs["visited"], theirs["favorite"]) == (False, True)
    assert theirs["others"][0]["display_name"] == "Alice" and theirs["others"][0]["notes"] == "wings!"

    assert client.get("/api/stats").json()["visited"] == 1 and client.get("/api/stats").json()["favorites"] == 0
    assert bob.get("/api/stats").json()["visited"] == 0 and bob.get("/api/stats").json()["favorites"] == 1


def test_people_with_nothing_logged_are_not_listed(client, bob):
    assert places_by_name(client)["Test Cafe"]["others"] == []


# ---- accounts -----------------------------------------------------------------------------

def test_first_account_takes_over_pre_login_visits(write_export):
    from app.models import Visit

    engine = create_engine("sqlite://")
    init_db(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as s:
        run([write_export([row(post_url="u1")])], s)
        place = s.scalars(select(Place)).one()
        s.add(Visit(place=place, user="me", visited=True, rating=4))
        s.commit()
        _, taken = add_user(s, "davy", "Davy", "long-enough-pw")
        assert taken == 1
        assert s.scalars(select(Visit)).one().user == "davy"
        _, taken = add_user(s, "alex", "Alex", "long-enough-pw")
        assert taken == 0


def test_add_user_validation(db):
    with db() as s:
        with pytest.raises(ValueError, match="already exists"):
            add_user(s, "ALICE", "x", "long-enough-pw")
        with pytest.raises(ValueError, match="at least 8"):
            add_user(s, "carol", "Carol", "short")
        with pytest.raises(ValueError, match="letters, numbers"):
            add_user(s, "carol smith", "Carol", "long-enough-pw")


def test_changing_password_logs_out_devices(db):
    from app.users import set_password

    c = login("alice")
    with db() as s:
        set_password(s, "alice", "brand-new-password")
    assert c.get("/api/places").status_code == 401
