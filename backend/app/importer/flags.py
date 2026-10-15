"""Per-reel flags: what is missing or questionable in a reel's JSON row."""

import re

from app.importer.parse import RawReel

CONFIDENCES = ("high", "medium", "low", "none")

# Generous box around the Bay Area; also catches swapped or zeroed lat/lng.
BAY_AREA_LAT = (36.8, 38.9)
BAY_AREA_LNG = (-123.6, -121.2)

FLAG_DESCRIPTIONS = {
    "no_venue": "venue is empty",
    "no_address": "address is empty",
    "city_only_address": "address is only a city, so the pin is a city centre",
    "no_street_address": "address has no street number (landmark, intersection or ZIP), so the pin may be rough",
    "no_city": "city is empty",
    "no_coords": "lat/lng missing or not a number",
    "coords_outside_bay_area": "lat/lng outside the Bay Area",
    "no_confidence": "confidence missing or not high/medium/low/none",
    "multi_spot": "reel covers several spots; only one is pinned",
}

_COUNTRY_SUFFIX = re.compile(r",\s*(United States|USA|US)\s*$", re.IGNORECASE)
_STATE_PART = re.compile(r"^CA(\s+\d{5}(-\d{4})?)?$", re.IGNORECASE)
_MULTI_SPOT = re.compile(r"multi[- ]spot|covers \d+|\b\d+ (spots|shops|places|restaurants)\b", re.IGNORECASE)


def is_city_only(address: str) -> bool:
    """True for "Oakland, CA, United States" or "Oakland, CA 94607"."""
    parts = [p.strip() for p in _COUNTRY_SUFFIX.sub("", address).split(",")]
    return len(parts) <= 2 and bool(_STATE_PART.match(parts[-1]))


def has_street_number(address: str) -> bool:
    return any(p.strip()[:1].isdigit() for p in address.split(","))


def in_bay_area(lat: float, lng: float) -> bool:
    return BAY_AREA_LAT[0] <= lat <= BAY_AREA_LAT[1] and BAY_AREA_LNG[0] <= lng <= BAY_AREA_LNG[1]


def compute_flags(reel: RawReel) -> list[str]:
    flags = []
    if not reel.venue:
        flags.append("no_venue")
    if not reel.address:
        flags.append("no_address")
    elif is_city_only(reel.address):
        flags.append("city_only_address")
    elif not has_street_number(reel.address):
        flags.append("no_street_address")
    if not reel.city:
        flags.append("no_city")
    if reel.lat is None or reel.lng is None:
        flags.append("no_coords")
    elif not in_bay_area(reel.lat, reel.lng):
        flags.append("coords_outside_bay_area")
    if reel.confidence not in CONFIDENCES:
        flags.append("no_confidence")
    if _MULTI_SPOT.search(reel.venue or "") or _MULTI_SPOT.search(reel.note or ""):
        flags.append("multi_spot")
    return flags
