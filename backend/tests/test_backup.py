import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.backup import export_log, restore_log, write_log
from app.db import init_db
from app.importer.run import run
from app.models import Place, Visit
from tests.conftest import row

ROWS = [
    row(venue="Stans Donuts", post_url="https://ig/u1"),
    row(venue="Stans Donuts", post_url="https://ig/u2", posted_by="other"),  # same place, second reel
    row(venue="Tacko", address="2 Other St, Oakland, CA 94607", post_url="https://ig/u3"),
    row(venue="Plain", address="3 Third St, Oakland, CA 94607", post_url="https://ig/u4"),
]


def fresh_session(write_export):
    engine = create_engine("sqlite://")
    init_db(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    run([write_export(ROWS)], s)
    return s


def place(s, name):
    return next(p for p in s.query(Place).all() if p.name == name)


def log_some(s):
    from datetime import date

    stans, tacko = place(s, "Stans Donuts"), place(s, "Tacko")
    s.add(Visit(place=stans, user="davy", visited=True, visited_date=date(2026, 10, 12), rating=5, notes="go early"))
    s.add(Visit(place=tacko, user="davy", favorite=True))
    s.add(Visit(place=stans, user="alex", favorite=True))
    tacko.tags_override = ["Mexican", "Seafood"]
    s.commit()


def test_export_is_per_person_with_shared_tags(write_export):
    s = fresh_session(write_export)
    log_some(s)
    assert export_log(s) == {
        "version": 2,
        "users": {
            "alex": {"places": [{"name": "Stans Donuts", "post_urls": ["https://ig/u1", "https://ig/u2"], "favorite": True}]},
            "davy": {
                "places": [
                    {
                        "name": "Stans Donuts",
                        "post_urls": ["https://ig/u1", "https://ig/u2"],
                        "visited": True,
                        "visited_date": "2026-10-12",
                        "rating": 5,
                        "notes": "go early",
                    },
                    {"name": "Tacko", "post_urls": ["https://ig/u3"], "favorite": True},
                ]
            },
        },
        "tags": [{"name": "Tacko", "post_urls": ["https://ig/u3"], "tags": ["Mexican", "Seafood"]}],
    }


def test_round_trip_onto_a_fresh_database(write_export, tmp_path):
    a = fresh_session(write_export)
    log_some(a)
    path = tmp_path / "log.json"
    write_log(a, path)

    b = fresh_session(write_export)  # e.g. the hosted server: re-imported, nothing logged
    restored, unmatched = restore_log(b, json.loads(path.read_text(encoding="utf-8")))
    assert (restored, unmatched) == (4, [])
    assert export_log(b) == export_log(a)


def test_version_1_file_restores_into_the_named_user(write_export):
    s = fresh_session(write_export)
    v1 = {
        "version": 1,
        "places": [
            {"name": "Stans Donuts", "post_urls": ["https://ig/u2", "https://ig/not-imported"], "rating": 4, "visited": True},
            {"name": "Tacko", "post_urls": ["https://ig/u3"], "tags": ["Mexican"]},
            {"name": "Gone", "post_urls": ["https://ig/missing"], "favorite": True},
        ],
    }
    restored, unmatched = restore_log(s, v1, v1_user="davy")
    assert unmatched == ["Gone"]
    out = export_log(s)
    assert out["users"]["davy"]["places"][0]["rating"] == 4
    assert out["tags"] == [{"name": "Tacko", "post_urls": ["https://ig/u3"], "tags": ["Mexican"]}]


def test_write_log_is_stable(write_export, tmp_path):
    s = fresh_session(write_export)
    log_some(s)
    path = tmp_path / "log.json"
    write_log(s, path)
    first, mtime = path.read_text(encoding="utf-8"), path.stat().st_mtime_ns
    write_log(s, path)  # nothing changed: file untouched
    assert path.read_text(encoding="utf-8") == first and path.stat().st_mtime_ns == mtime
    assert "id" not in json.loads(first)["users"]["davy"]["places"][0]  # no database ids
