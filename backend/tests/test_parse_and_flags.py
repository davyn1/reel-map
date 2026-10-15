import pytest

from app.importer.flags import compute_flags, is_city_only
from app.importer.parse import ExportParseError, load_file
from tests.conftest import REAL_EXPORT, row


def test_empty_string_and_null_are_both_unknown(write_export):
    path = write_export([row(venue="", address=None, lat="", lng=None, note="  ")])
    reel = load_file(path).reels[0]
    assert reel.venue is None and reel.address is None and reel.note is None
    assert reel.lat is None and reel.lng is None


def test_missing_and_extra_keys_are_tolerated(write_export):
    r = row(surprise="x")
    del r["dish"], r["city"]
    reel = load_file(write_export([r])).reels[0]
    assert reel.dish is None and reel.city is None and reel.venue == "Test Cafe"


def test_numeric_strings_become_coords(write_export):
    reel = load_file(write_export([row(lat="37.8", lng=" -122.27 ")])).reels[0]
    assert (reel.lat, reel.lng) == (37.8, -122.27)


def test_rows_without_post_url_or_not_objects_are_skipped(write_export):
    parsed = load_file(write_export([row(post_url=""), "oops", row()]))
    assert len(parsed.reels) == 1
    assert [i for i, _ in parsed.skipped] == [0, 1]


def test_parse_error_reports_location(write_export):
    path = write_export('[\n {"venue": "A",}\n]')
    with pytest.raises(ExportParseError, match=r"line 2, column 16"):
        load_file(path)


def test_top_level_must_be_array(write_export):
    with pytest.raises(ExportParseError, match="expected a JSON array"):
        load_file(write_export({"venue": "A"}))


@pytest.mark.parametrize(
    "address, expected",
    [
        ("Oakland, CA, United States", True),
        ("San Jose, CA 95112", True),
        ("Stanford Shopping Center, Palo Alto, CA", False),
        ("Matzip, 33592 Alvarado Niles Rd, Union City, CA 94587-3111, United States", False),
    ],
)
def test_city_only(address, expected):
    assert is_city_only(address) is expected


def test_flags(write_export):
    rows = [
        row(venue="", address="", city=None, lat=None, lng=None, confidence="none", post_url="u1"),
        row(address="Oakland, CA, United States", confidence="low", post_url="u2"),
        row(venue="Deli Board (multi-spot reel)", note="reel covers 3 sandwich shops", post_url="u3"),
        row(lat=-122.27, lng=37.8, post_url="u4"),  # swapped
        row(confidence="maybe", post_url="u5"),
        row(post_url="u6"),
        row(address="Industrial Pkwy SW & Whipple Rd, Hayward, CA 94544, United States", post_url="u7"),
    ]
    flags = [compute_flags(r) for r in load_file(write_export(rows)).reels]
    assert flags[0] == ["no_venue", "no_address", "no_city", "no_coords"]
    assert flags[1] == ["city_only_address"]
    assert flags[2] == ["multi_spot"]
    assert flags[3] == ["coords_outside_bay_area"]
    assert flags[4] == ["no_confidence"]
    assert flags[5] == []
    assert flags[6] == ["no_street_address"]


@pytest.mark.skipif(not REAL_EXPORT.exists(), reason="no real export")
def test_real_export_parses():
    parsed = load_file(REAL_EXPORT)
    assert len(parsed.reels) == 59 and not parsed.skipped
