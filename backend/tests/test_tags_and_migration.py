from sqlalchemy import create_engine, inspect, text

from app.db import init_db
from app.models import Place, Reel
from app.tags import place_tags


def tagged(name, dish="", note=""):
    return place_tags(Place(name=name, lat=0, lng=0, reels=[Reel(post_url="u", venue_raw=name, dish=dish, muse_note=note)]))


def test_tags_from_captions_and_notes():
    assert tagged("Pizza Gallery", "HOT LEMON PEPPER CHICKEN WINGS AND VODKA SAUCE PIZZA") == ["Pizza", "Fried chicken"]
    assert tagged("Tangjip", "best bossam", note="Korean") == ["Korean"]
    assert tagged("Stan’s Doughnut", "Seriously the best doughnut") == ["Donuts"]


def test_rice_burrito_is_not_mexican():
    assert tagged("Mitk Kitchen", "TAIWANESE RICE BURRITO WITH BRAISED PORK BELLY") == ["Taiwanese"]


def test_words_must_match_whole():
    assert tagged("Shrimpn Ain’t Eazy", "Da Grubby Chopped Cheese") == ["Sandwiches"]  # not Seafood
    assert tagged("Phoenix Diner") == []  # "pho" inside a word


def test_migration_adds_favorite_to_an_old_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:  # visits table as it was before favorites existed
        conn.execute(text("CREATE TABLE places (id INTEGER PRIMARY KEY, name VARCHAR, lat FLOAT, lng FLOAT, address VARCHAR, is_approximate BOOLEAN)"))
        conn.execute(text("CREATE TABLE visits (id INTEGER PRIMARY KEY, place_id INTEGER, user VARCHAR, visited BOOLEAN, visited_date DATE, rating INTEGER, notes TEXT)"))
        conn.execute(text("INSERT INTO places VALUES (1, 'A', 37.8, -122.2, NULL, 0)"))
        conn.execute(text("INSERT INTO visits VALUES (1, 1, 'me', 1, '2026-10-01', 4, 'good')"))
    init_db(engine)
    assert "favorite" in {c["name"] for c in inspect(engine).get_columns("visits")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT visited, rating, notes, favorite FROM visits")).one() == (1, 4, "good", 0)
    init_db(engine)  # running again is a no-op
