"""Trips: the Bay Area (home) map and maps for trips elsewhere.

Every place and reel belongs to one trip. The home trip is made automatically, with the generous
Bay Area box the importer always used, and everything from before trips existed belongs to it. A
trip's area is a lat/lng box: imports into it flag reels outside it for review, and places added by
hand must fall inside it. Muse uploads a trip's collection to /api/import?trip=<slug>.
"""

import re
import unicodedata
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Trip

HOME_SLUG = "bay-area"
HOME_NAME = "Bay Area"
# Generous box around the Bay Area; also catches swapped or zeroed lat/lng.
HOME_BOX = {"south": 36.8, "north": 38.9, "west": -123.6, "east": -121.2}
MAX_SPAN_DEG = 6.0  # a trip is a city or a region, not a country


def in_home_box(lat: float, lng: float) -> bool:
    """The home trip's area, for tools that look at export files without a database."""
    return HOME_BOX["south"] <= lat <= HOME_BOX["north"] and HOME_BOX["west"] <= lng <= HOME_BOX["east"]


def ensure_home(conn) -> None:
    """Called by init_db: make the home trip if it's missing, and give it everything that has no
    trip yet (places and reels from before trips existed). Plain SQL on the connection, so it runs
    before any session exists."""
    row = conn.execute(text("SELECT id FROM trips WHERE is_home = 1")).first()
    if row is None:
        conn.execute(
            text("INSERT INTO trips (slug, name, south, west, north, east, is_home, created_at) "
                 "VALUES (:slug, :name, :south, :west, :north, :east, 1, :at)"),
            {"slug": HOME_SLUG, "name": HOME_NAME, **HOME_BOX, "at": datetime.now(timezone.utc).replace(tzinfo=None)},
        )
        row = conn.execute(text("SELECT id FROM trips WHERE is_home = 1")).first()
    conn.execute(text("UPDATE places SET trip_id = :id WHERE trip_id IS NULL"), {"id": row[0]})
    conn.execute(text("UPDATE reels SET trip_id = :id WHERE trip_id IS NULL"), {"id": row[0]})


def home(session: Session) -> Trip:
    return session.scalars(select(Trip).where(Trip.is_home.is_(True))).one()


def by_slug(session: Session, slug: str) -> Trip | None:
    return session.scalars(select(Trip).where(Trip.slug == slug)).first()


def slugify(name: str) -> str:
    """"Tokyo 2027" -> "tokyo-2027"; "Ciudad de México" -> "ciudad-de-mexico"."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-") or "trip"


def unique_slug(session: Session, name: str) -> str:
    base = slugify(name)
    slug, n = base, 2
    while by_slug(session, slug) is not None:
        slug, n = f"{base}-{n}", n + 1
    return slug


def check_box(south: float, west: float, north: float, east: float) -> str | None:
    """Why a trip area is unusable, or None if it's fine."""
    if not (-90 <= south < north <= 90 and -180 <= west < east <= 180):
        return "That area isn't a valid box (south < north, west < east)."
    if north - south > MAX_SPAN_DEG or east - west > MAX_SPAN_DEG:
        return "That area is too big for a trip; pick a city or a region."
    return None
