"""Demo mode: the public, try-it-yourself copy of the app (FOOD_MAP_DEMO=true).

Runs as its own server with its own throwaway database, never the real one. On start, and again
every RESET_HOURS, the database is wiped and refilled with made-up places (sample_reels.json, in
Muse's export format, imported by the normal importer) and two accounts:

- DEMO_USERNAME / DEMO_PASSWORD: shown on the login screen ("Try the demo"); anyone can use it.
- "sam": the friend, with a log of their own, so friend mode has something to show.

Uploads are off, and the demo accounts are never locked out by wrong passwords.
"""

import asyncio
import os
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, engine, init_db
from app.importer.run import record_run, run
from app.models import Place, Visit
from app.users import add_user

DEMO = os.getenv("FOOD_MAP_DEMO", "").lower() in ("1", "true", "yes")
DEMO_USERNAME = "demo"
DEMO_PASSWORD = "try-the-demo"
FRIEND_USERNAME = "sam"
SOURCE_URL = "https://github.com/davyn1/reel-map"
RESET_HOURS = 24
SAMPLE = Path(__file__).with_name("sample_reels.json")

# (place name, user, visit fields): days_ago stands in for a visit date, so the dates stay recent.
_VISITS = [
    ("Seoul Spoon", DEMO_USERNAME, {"visited": True, "days_ago": 12, "rating": 5, "notes": "Get the soondubu, extra spicy", "favorite": True}),
    ("Casa Lumbre Taqueria", DEMO_USERNAME, {"visited": True, "days_ago": 30, "rating": 4, "notes": "Birria tacos > quesotaco"}),
    ("Park Street Donut Co", DEMO_USERNAME, {"visited": True, "days_ago": 5, "rating": 3}),
    ("Ramen Kumo", DEMO_USERNAME, {"favorite": True}),
    ("Saltwater Oyster Bar", DEMO_USERNAME, {"favorite": True, "notes": "Happy hour is 3-5pm"}),
    ("Hot Pot Harbor", DEMO_USERNAME, {"favorite": True}),
    ("Ramen Kumo", FRIEND_USERNAME, {"visited": True, "days_ago": 20, "rating": 5, "notes": "Worth the line"}),
    ("Saltwater Oyster Bar", FRIEND_USERNAME, {"favorite": True}),
    ("Hot Pot Harbor", FRIEND_USERNAME, {"favorite": True}),
    ("Slice Theory", FRIEND_USERNAME, {"visited": True, "days_ago": 8, "rating": 4, "notes": "Hot honey pepperoni"}),
    ("Seoul Spoon", FRIEND_USERNAME, {"visited": True, "days_ago": 40, "rating": 4}),
    ("Mochi Moon Bakery", FRIEND_USERNAME, {"favorite": True}),
]


def reset(bind=engine) -> None:
    """Wipe the demo database and fill it with the sample data."""
    Base.metadata.drop_all(bind)
    init_db(bind)
    with Session(bind, expire_on_commit=False) as session:
        record_run(session, "cli", SAMPLE.name, run([SAMPLE], session))
        add_user(session, DEMO_USERNAME, "Demo", DEMO_PASSWORD)
        # Nobody logs in as the friend; a random password keeps it that way.
        add_user(session, FRIEND_USERNAME, "Sam", os.urandom(24).hex())
        places = {p.name: p for p in session.scalars(select(Place))}
        for name, user, fields in _VISITS:
            fields = dict(fields)
            days_ago = fields.pop("days_ago", None)
            if days_ago is not None:
                fields["visited_date"] = date.today() - timedelta(days=days_ago)
            session.add(Visit(place=places[name], user=user, **fields))
        session.commit()


async def reset_periodically() -> None:
    while True:
        await asyncio.sleep(RESET_HOURS * 3600)
        await asyncio.to_thread(reset)
