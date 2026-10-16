from sqlalchemy import create_engine, inspect, text

from app.db import init_db
from app.models import Place, Reel
from app.tags import place_tags


def tagged(name, dish="", note=""):
    return place_tags(Place(name=name, lat=0, lng=0, reels=[Reel(post_url="u", venue_raw=name, dish=dish, muse_note=note)]))


def test_broad_cuisine_tags():
    assert tagged("Pizza Gallery", "HOT LEMON PEPPER CHICKEN WINGS AND VODKA SAUCE PIZZA") == ["Pizza & Italian"]
    assert tagged("Tangjip", "best bossam", note="Korean") == ["Korean"]
    assert tagged("The Burger Shop", "ONE OF MY FAVORITE SMASHBURGERS") == ["American"]


def test_american_only_when_no_other_cuisine():
    # fried chicken at a Korean spot is Korean, not American too
    assert tagged("Matzip Korean Restaurant", "best Asian fried chicken wings") == ["Korean"]
    assert tagged("Sweetheart Cafe", "popcorn chicken + boba") == ["Chinese", "Sweets & bakery"]


def test_groups_sit_alongside_cuisines():
    assert tagged("Stan’s Doughnut", "Seriously the best doughnut") == ["Sweets & bakery"]
    assert tagged("Hyphy Burger", "FRUITY PEBBLES MILKSHAKE") == ["American", "Sweets & bakery"]
    assert tagged("GAO's BBQ & Crab", "giant oysters, $1 skewers") == ["Chinese", "Seafood"]


def test_taiwanese_rice_burrito_is_chinese_not_mexican():
    assert tagged("Mitk Kitchen", "TAIWANESE RICE BURRITO WITH BRAISED PORK BELLY") == ["Chinese"]


def test_italian_words_at_soul_food_spots_dont_make_it_italian():
    assert tagged("Rome's Kitchen", "BRISKET MAC N CHEESE, ITALIAN GARLIC SALMON MASH") == ["American"]


def test_words_must_match_whole():
    assert tagged("Shrimpn Ain’t Eazy", "Da Grubby Chopped Cheese") == ["American"]  # "shrimpn" isn't seafood
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
