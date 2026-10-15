import pytest
from sqlalchemy import func, select

from app.importer.parse import ExportParseError
from app.importer.run import run
from app.maps_link import google_maps_url
from app.models import Place, Reel
from tests.conftest import REAL_EXPORT, row

URL = "https://www.instagram.com/reel/A1/"


def reels(session):
    return {r.post_url: r for r in session.scalars(select(Reel))}


def place_count(session):
    return session.scalar(select(func.count(Place.id)))


def test_high_confidence_is_pinned_at_muse_coords(session, write_export):
    r = row(venue="CLAIRE’S CRUNCH CAKE", address="Matzip, 33592 Alvarado Niles Rd, Union City, CA 94587-3111, United States")
    s = run([write_export([r])], session)
    place = reels(session)[URL].place
    assert (place.lat, place.lng, place.is_approximate) == (37.8, -122.27, False)
    assert place.name == "Claire’s Crunch Cake"
    assert place.address == "33592 Alvarado Niles Rd, Union City, CA 94587-3111"
    assert (s.imported, s.pinned) == (1, 1)


def test_reimport_only_adds_new_reels(session, write_export):
    run([write_export([row()])], session)
    s = run([write_export([row(), row(post_url="u2")])], session)
    assert (s.imported, s.skipped, s.merged) == (1, 1, 1)
    assert session.scalar(select(func.count(Reel.id))) == 2
    assert place_count(session) == 1


def test_spelling_variants_at_one_address_merge(session, write_export):
    rows = [
        row(venue="Stans Donuts", address="2628 Homestead Rd, Santa Clara, CA 95051-5351, United States", post_url="u1"),
        row(venue="Stan's Doughnut", address="Stan's Donut Shop, 2628 Homestead Rd, Santa Clara, CA 95051, United States", post_url="u2"),
    ]
    s = run([write_export(rows)], session)
    assert place_count(session) == 1 and s.merged == 1


def test_same_name_different_address_is_not_merged(session, write_export):
    rows = [row(post_url="u1"), row(address="2 Other St, Oakland, CA 94607", post_url="u2")]
    run([write_export(rows)], session)
    assert place_count(session) == 2


def test_same_address_different_name_is_not_merged(session, write_export):
    run([write_export([row(venue="Food Hall Tacos", post_url="u1"), row(venue="Food Hall Ramen", post_url="u2")])], session)
    assert place_count(session) == 2


def test_low_confidence_is_approximate_and_pop_ups_in_one_city_stay_separate(session, write_export):
    oakland = dict(address="Oakland, CA, United States", city="Oakland", lat=37.80508, lng=-122.27307, confidence="low")
    rows = [
        row(venue="Its On The Flo", post_url="u1", **oakland),
        row(venue="Its On The Flo", post_url="u2", **oakland),
        row(venue="Loaded Mac N Gritz", post_url="u3", **oakland),
    ]
    s = run([write_export(rows)], session)
    found = session.scalars(select(Place)).all()
    assert sorted(p.name for p in found) == ["Its On The Flo", "Loaded Mac N Gritz"]
    assert all(p.is_approximate for p in found)
    assert (s.approximate, s.merged) == (3, 1)


def test_same_pop_up_in_two_cities_is_two_places(session, write_export):
    rows = [
        row(venue="Cuchi Tacos", address="Castro Valley, CA, United States", city="Castro Valley", confidence="low", post_url="u1"),
        row(venue="Cuchi Tacos", address="Hayward, CA, United States", city="Hayward", confidence="low", post_url="u2"),
    ]
    run([write_export(rows)], session)
    assert place_count(session) == 2


def test_city_only_address_with_high_confidence_is_approximate(session, write_export):
    run([write_export([row(address="Oakland, CA, United States")])], session)
    reel = reels(session)[URL]
    assert reel.status == "matched" and reel.place.is_approximate


def test_none_confidence_needs_review(session, write_export):
    run([write_export([row(venue="", address="", lat=None, lng=None, confidence="none")])], session)
    reel = reels(session)[URL]
    assert reel.status == "needs_review" and reel.place is None
    assert "no_venue" in reel.flags and "venue is empty" in reel.review_reason


def test_swapped_coords_need_review(session, write_export):
    run([write_export([row(lat=-122.27, lng=37.8)])], session)
    reel = reels(session)[URL]
    assert reel.status == "needs_review" and reel.place is None


def test_multi_spot_is_pinned_and_flagged_for_review(session, write_export):
    r = row(venue="Deli Board (multi-spot reel)", note="reel covers 3 sandwich shops")
    s = run([write_export([r])], session)
    reel = reels(session)[URL]
    assert reel.status == "needs_review" and reel.place.name == "Deli Board"
    assert (s.needs_review, s.pinned_needing_review) == (1, 1)


def test_bad_file_aborts_before_writing(session, write_export):
    good = write_export([row()], "reels_a.json")
    bad = write_export("[{", "reels_b.json")
    with pytest.raises(ExportParseError):
        run([good, bad], session)
    assert session.scalar(select(func.count(Reel.id))) == 0


def test_google_maps_url():
    url = google_maps_url("Claire’s Crunch Cake", "233 N Grant St, San Mateo, CA 94401", 37.5, -122.3)
    assert url.startswith("https://www.google.com/maps/search/?api=1&query=Claire")
    assert "233+N+Grant+St" in url
    assert google_maps_url("X", None, 37.5, -122.3).endswith("query=37.5%2C-122.3")


@pytest.mark.skipif(not REAL_EXPORT.exists(), reason="no real export")
def test_real_export_every_row_accounted_for(session):
    s = run([REAL_EXPORT], session)
    assert s.imported == 59
    assert s.pinned + s.approximate + s.needs_review == s.imported
    for reel in session.scalars(select(Reel).where(Reel.status == "matched")):
        assert reel.place is not None
