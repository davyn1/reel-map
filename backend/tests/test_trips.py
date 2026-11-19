"""Trips: a Bay Area (home) map plus maps for trips elsewhere, each with its own places and area."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app import trips
from app.backup import export_log, restore_log
from app.db import init_db
from app.importer.run import run
from app.main import app
from app.models import Place, Reel, Trip
from tests.conftest import row
from tests.test_api import bob, client, db, login, places_by_name, review_by_url  # noqa: F401  (fixtures)
from tests.test_backup import fresh_session
from tests.test_imports import TOKEN, post, token  # noqa: F401  (fixture)

# Around central Tokyo, about what the app makes from a city search.
TOKYO = {"name": "Tokyo 2027", "south": 35.5, "west": 139.4, "north": 35.9, "east": 140.0}
TOKYO_REELS = [
    row(venue="Ramen Spot", address="1-2-3 Shibuya, Tokyo", city="Tokyo", lat=35.66, lng=139.70,
        post_url="https://www.instagram.com/reel/TOK1/"),
    row(venue="Sushi Counter", address="4-5-6 Ginza, Tokyo", city="Tokyo", lat=35.67, lng=139.76,
        post_url="https://www.instagram.com/reel/TOK2/"),
    row(venue="Stray Oakland Pin", address="1 Main St, Oakland, CA", city="Oakland", lat=37.8, lng=-122.27,
        post_url="https://www.instagram.com/reel/TOK3/"),
]


def make_tokyo(client) -> dict:
    res = client.post("/api/trips", json=TOKYO)
    assert res.status_code == 201, res.text
    return res.json()


def test_home_trip_holds_what_was_there_before_trips(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:  # places as they were before trips existed
        conn.execute(text("CREATE TABLE places (id INTEGER PRIMARY KEY, name VARCHAR, lat FLOAT, lng FLOAT, address VARCHAR, is_approximate BOOLEAN)"))
        conn.execute(text("INSERT INTO places VALUES (1, 'A', 37.8, -122.2, NULL, 0)"))
    init_db(engine)
    init_db(engine)  # running again makes no second home trip
    with engine.connect() as conn:
        home = conn.execute(text("SELECT id, slug, name FROM trips WHERE is_home = 1")).all()
        assert [(h[1], h[2]) for h in home] == [("bay-area", "Bay Area")]
        assert conn.execute(text("SELECT trip_id FROM places")).scalar() == home[0][0]


def test_create_list_rename_and_delete_trips(client):
    trips_now = client.get("/api/trips").json()
    assert [(t["name"], t["is_home"]) for t in trips_now] == [("Bay Area", True)]
    assert trips_now[0]["places"] == 3  # the fixture's places

    tokyo = make_tokyo(client)
    assert tokyo["slug"] == "tokyo-2027" and tokyo["places"] == 0 and not tokyo["is_home"]
    assert [t["name"] for t in client.get("/api/trips").json()] == ["Bay Area", "Tokyo 2027"]
    assert client.post("/api/trips", json=TOKYO).status_code == 409  # same name

    renamed = client.patch(f"/api/trips/{tokyo['id']}", json={"name": "Japan Spring"}).json()
    assert renamed["name"] == "Japan Spring" and renamed["slug"] == "tokyo-2027"  # Muse's address stays

    home_id = client.get("/api/trips").json()[0]["id"]
    assert client.delete(f"/api/trips/{home_id}").status_code == 409
    assert client.delete(f"/api/trips/{tokyo['id']}").status_code == 204
    assert [t["name"] for t in client.get("/api/trips").json()] == ["Bay Area"]


def test_a_trip_area_must_be_a_sensible_box(client):
    bad = [
        {**TOKYO, "north": 35.4},  # north below south
        {**TOKYO, "south": 20.0},  # a country, not a city
        {**TOKYO, "east": 200.0},
    ]
    for body in bad:
        assert client.post("/api/trips", json=body).status_code == 422
    assert client.post("/api/trips", json={**TOKYO, "name": "  "}).status_code == 422


def test_import_into_a_trip_keeps_its_places_apart(client, token, uploads_in_tmp):
    tokyo = make_tokyo(client)
    res = post(TOKYO_REELS, c=None)
    assert res.status_code == 200
    # Without ?trip= it went to the Bay Area: the Tokyo pins are outside it, so they wait for review.
    assert res.json()["needs_review"] == 2

    res = client.post("/api/import?trip=tokyo-2027", json=[
        {**r, "post_url": r["post_url"].replace("TOK", "TKY")} for r in TOKYO_REELS
    ])
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["trip"] == "tokyo-2027" and (body["pinned"], body["needs_review"]) == (2, 1)
    assert (uploads_in_tmp / "trips" / "tokyo-2027" / body["saved_as"]).exists()

    in_tokyo = client.get(f"/api/places?trip={tokyo['id']}").json()
    assert sorted(p["name"] for p in in_tokyo) == ["Ramen Spot", "Sushi Counter"]
    assert all(p["trip_id"] == tokyo["id"] for p in in_tokyo)
    assert "Ramen Spot" not in places_by_name(client)  # the default list is the Bay Area's
    assert len(client.get("/api/places?trip=all").json()) == len(places_by_name(client)) + 2

    stray = next(r for r in client.get("/api/reels/review").json() if r["post_url"].endswith("TKY3/"))
    assert stray["trip"]["name"] == "Tokyo 2027" and "coords_outside_area" in stray["flags"]


def test_unknown_trip_upload_is_refused(client, token):
    res = TestClient(app).post("/api/import?trip=nowhere", json=TOKYO_REELS[:1], headers={"Authorization": f"Bearer {TOKEN}"})
    assert res.status_code == 404 and "nowhere" in res.json()["detail"]


def test_places_merge_only_within_their_trip(db, write_export):
    """Same name and address in two trips are two places (merging would pull a pin across the world)."""
    with db() as s:
        tokyo = Trip(slug="tokyo", name="Tokyo", south=35.5, west=139.4, north=35.9, east=140.0, is_home=False,
                     created_at=trips.home(s).created_at)
        s.add(tokyo)
        s.commit()
        same = dict(venue="Twin Cafe", address="1 Main St, Oakland, CA 94607", city="Oakland")
        run([write_export([row(**same, lat=37.8, lng=-122.27, post_url="m1")], "a.json")], s)
        run([write_export([row(**same, lat=35.66, lng=139.70, post_url="m2")], "b.json")], s, tokyo)
        twins = s.query(Place).filter(Place.name == "Twin Cafe").all()
        assert len(twins) == 2 and {p.trip_id for p in twins} == {trips.home(s).id, tokyo.id}


def test_adding_by_hand_checks_the_trips_area(client):
    tokyo = make_tokyo(client)
    in_tokyo = {"name": "Kissaten", "lat": 35.68, "lng": 139.77, "trip_id": tokyo["id"]}
    res = client.post("/api/places", json=in_tokyo)
    assert res.status_code == 201 and res.json()["trip_id"] == tokyo["id"]
    res = client.post("/api/places", json={**in_tokyo, "name": "Somewhere Else", "lat": 37.8, "lng": -122.27})
    assert res.status_code == 422 and "Tokyo 2027" in res.json()["detail"]
    # No trip named: the Bay Area, where a Tokyo pin is out of bounds.
    assert client.post("/api/places", json={"name": "Lost", "lat": 35.68, "lng": 139.77}).status_code == 422
    assert client.delete(f"/api/trips/{tokyo['id']}").status_code == 409  # not empty any more


def test_fixing_a_reel_uses_its_trips_area(client):
    tokyo = make_tokyo(client)
    client.post("/api/import?trip=tokyo-2027", json=[TOKYO_REELS[2]])  # an Oakland pin in the Tokyo trip
    reel = review_by_url(client)[TOKYO_REELS[2]["post_url"]]
    oakland = {"name": "Nope", "lat": 37.8, "lng": -122.27}
    assert client.post(f"/api/reels/{reel['id']}/place", json={"new_place": oakland}).status_code == 422
    fixed = client.post(f"/api/reels/{reel['id']}/place", json={"new_place": {"name": "Right Spot", "lat": 35.7, "lng": 139.7}})
    assert fixed.status_code == 200
    assert [p["name"] for p in client.get(f"/api/places?trip={tokyo['id']}").json()] == ["Right Spot"]


def test_stats_count_visits_per_trip(client):
    tokyo = make_tokyo(client)
    kissa = client.post("/api/places", json={"name": "Kissaten", "lat": 35.68, "lng": 139.77, "trip_id": tokyo["id"],
                                             "visited": True}).json()
    assert kissa["visited"]
    home_visited = client.get("/api/stats").json()["visited"]
    assert client.get(f"/api/stats?trip={tokyo['id']}").json()["visited"] == 1
    assert client.get("/api/stats").json()["visited"] == home_visited  # the Bay Area's own count


def test_backup_keeps_trips_and_their_hand_added_places(write_export):
    s = fresh_session(write_export)
    tokyo = Trip(slug="tokyo-2027", name="Tokyo 2027", south=35.5, west=139.4, north=35.9, east=140.0,
                 is_home=False, created_at=trips.home(s).created_at)
    s.add(tokyo)
    s.commit()
    place = Place(name="Kissaten", lat=35.68, lng=139.77, trip=tokyo)
    s.add(place)
    s.add(Reel(post_url="manual:abc", venue_raw="Kissaten", place=place, status="matched", flags=[],
               source_file="manual", added_by="alex", trip=tokyo))
    s.commit()
    data = export_log(s)
    assert data["trips"] == [{"slug": "tokyo-2027", "name": "Tokyo 2027", "south": 35.5, "west": 139.4,
                              "north": 35.9, "east": 140.0}]
    assert next(m for m in data["manual_places"] if m["name"] == "Kissaten")["trip"] == "tokyo-2027"

    fresh = fresh_session(write_export)  # a new database: no Tokyo trip yet
    restore_log(fresh, data)
    restored = fresh.query(Place).filter(Place.name == "Kissaten").one()
    assert restored.trip.slug == "tokyo-2027" and restored.trip.contains(35.68, 139.77)
