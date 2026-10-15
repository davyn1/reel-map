"""Name similarity and address normalization for deciding which reels share a place."""

import re
import unicodedata

from rapidfuzz import fuzz

from app.importer.flags import is_city_only

# Two reels at the same street address are one place only if their names are this similar.
# "Stans Donuts" vs "Stan's Doughnut" scores 85; "Food Hall Tacos" vs "Food Hall Ramen" scores 73.
MIN_MERGE_NAME_SCORE = 80.0

_PARENS = re.compile(r"\([^)]*\)")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_ZIP = re.compile(r"\bca\s+(\d{5})(-\d{4})?\b")
_COUNTRY = re.compile(r",\s*(united states|usa|us)\s*$")
_STREET_WORDS = {
    "street": "st", "avenue": "ave", "boulevard": "blvd", "road": "rd", "drive": "dr",
    "place": "pl", "lane": "ln", "court": "ct", "parkway": "pkwy", "highway": "hwy",
    "north": "n", "south": "s", "east": "e", "west": "w", "suite": "ste",
}


def clean_venue(venue: str) -> str:
    """Drop Muse annotations like "(multi-spot reel)"."""
    return _PARENS.sub("", venue).strip()


def normalize_name(name: str) -> str:
    text = unicodedata.normalize("NFKD", clean_venue(name)).encode("ascii", "ignore").decode()
    text = text.lower().replace("&", " and ").replace("'", "")
    return " ".join(_NON_ALNUM.sub(" ", text).split())


def name_score(a: str, b: str) -> float:
    """0-100. Handles extra words ("Hed" vs "Hed Very Thai") and spacing ("Tangjip" vs "Tang Jip").

    Full credit for extra words only when one name's words are all in the other, so
    "Food Hall Tacos" vs "Food Hall Ramen" stays low despite the shared words.
    """
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    ta, tb = set(na.split()), set(nb.split())
    words = 100.0 if ta <= tb or tb <= ta else fuzz.token_sort_ratio(na, nb)
    spacing = fuzz.ratio(na.replace(" ", ""), nb.replace(" ", ""))
    return max(words, spacing if spacing >= 90 else 0.0)


def normalize_address(address: str | None) -> str | None:
    """Comparable key "<number street> <zip or city>", or None if there is no street address.

    "Matzip, 33592 Alvarado Niles Rd, Union City, CA 94587-3111, United States"
    -> "33592 alvarado niles rd 94587"
    """
    if not address or is_city_only(address):
        return None
    text = unicodedata.normalize("NFKD", address).encode("ascii", "ignore").decode().lower().strip()
    text = _COUNTRY.sub("", text)
    parts = [p.strip() for p in text.split(",") if p.strip()]
    street_i = next((i for i, p in enumerate(parts) if p[:1].isdigit()), None)
    if street_i is None:
        return None
    street = " ".join(_STREET_WORDS.get(w, w) for w in _NON_ALNUM.sub(" ", parts[street_i]).split())
    zip_match = _ZIP.search(text)
    tail = zip_match.group(1) if zip_match else _NON_ALNUM.sub(" ", parts[street_i + 1]).strip() if street_i + 1 < len(parts) else ""
    return f"{street} {tail}".strip()


def display_name(venue: str) -> str:
    """Venue without Muse annotations; ALL-CAPS captions become "Claire’s Crunch Cake"."""
    name = clean_venue(venue)
    if name.isupper():
        name = re.sub(r"(^|[\s+/-])([a-z])", lambda m: m.group(1) + m.group(2).upper(), name.lower())
    return name


def display_address(address: str | None) -> str | None:
    """Drop the business-name prefix and country: "Matzip, 33592 Alvarado Niles Rd, Union City, CA 94587"."""
    if not address:
        return None
    text = re.sub(r",\s*(United States|USA|US)\s*$", "", address.strip(), flags=re.IGNORECASE)
    parts = [p.strip() for p in text.split(",")]
    street_i = next((i for i, p in enumerate(parts) if p[:1].isdigit()), 0)
    return ", ".join(parts[street_i:])
