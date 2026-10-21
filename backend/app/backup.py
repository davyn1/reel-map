"""Your personal log as a small, readable JSON file: personal/my-log.json.

The database can be rebuilt from Muse exports, except what you added by hand: been-here,
visit dates, ratings, notes, favorites and hand-picked tags. That part is written here after
every change, so it can be committed and restored onto a fresh database.

Places are identified by their reels' post URLs (stable across re-imports), not database IDs.
Output is sorted and has no timestamps, so a commit's diff shows only what you changed.

All personal data in the repo lives under personal/; see the README to remove it.

    python -m app.backup export      # write personal/my-log.json from the database
    python -m app.backup restore     # apply personal/my-log.json to the database
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import PERSONAL_DIR
from app.models import Place, Reel, Visit

LOG_PATH = PERSONAL_DIR / "my-log.json"
USER = "me"
VERSION = 1


def _post_urls(place: Place) -> list[str]:
    return sorted({r.post_url for r in [*place.reels, *place.extra_reels]})


def _entry(place: Place) -> dict | None:
    visit = next((v for v in place.visits if v.user == USER), None)
    entry: dict = {"name": place.name, "post_urls": _post_urls(place)}
    if visit and visit.visited:
        entry["visited"] = True
        if visit.visited_date:
            entry["visited_date"] = visit.visited_date.isoformat()
        if visit.rating:
            entry["rating"] = visit.rating
    if visit and visit.notes:
        entry["notes"] = visit.notes
    if visit and visit.favorite:
        entry["favorite"] = True
    if place.tags_override is not None:
        entry["tags"] = place.tags_override
    return entry if len(entry) > 2 else None  # only name + post_urls: nothing logged


def export_log(session: Session) -> dict:
    places = session.scalars(
        select(Place).options(selectinload(Place.reels), selectinload(Place.extra_reels), selectinload(Place.visits))
    )
    entries = [e for p in places if (e := _entry(p)) and e["post_urls"]]
    entries.sort(key=lambda e: (e["name"].lower(), e["post_urls"][0]))
    return {"version": VERSION, "places": entries}


def write_log(session: Session, path: Path | None = None) -> None:
    """Rewrite the log file, only if its content changed (keeps file times and git quiet)."""
    path = path or LOG_PATH
    text = json.dumps(export_log(session), indent=2, ensure_ascii=False) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def save_log_quietly(session: Session) -> None:
    """Called after every change to logged data. A failed write must never fail the request."""
    try:
        write_log(session)
    except Exception as e:  # noqa: BLE001
        logging.getLogger(__name__).warning("could not write %s: %s", LOG_PATH, e)


def restore_log(session: Session, data: dict) -> tuple[int, list[str]]:
    """Apply a log to the database. Returns (places restored, names of entries with no matching place)."""
    from datetime import date

    restored, unmatched = 0, []
    for entry in data.get("places", []):
        reel = session.scalars(select(Reel).where(Reel.post_url.in_(entry.get("post_urls", [])))).first()
        place = None
        if reel is not None:
            place = reel.place or (reel.extra_places[0] if reel.extra_places else None)
        if place is None:
            unmatched.append(entry.get("name", "?"))
            continue
        visit = next((v for v in place.visits if v.user == USER), None)
        if visit is None:
            visit = Visit(place=place, user=USER)
            session.add(visit)
        visit.visited = bool(entry.get("visited"))
        visit.visited_date = date.fromisoformat(entry["visited_date"]) if entry.get("visited_date") else None
        visit.rating = entry.get("rating")
        visit.notes = entry.get("notes")
        visit.favorite = bool(entry.get("favorite"))
        place.tags_override = entry.get("tags")
        restored += 1
    session.commit()
    return restored, unmatched


def main(argv=None) -> int:
    from app.db import SessionLocal, init_db

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["export", "restore"])
    parser.add_argument("--file", type=Path, default=LOG_PATH)
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    init_db()
    with SessionLocal() as session:
        if args.action == "export":
            write_log(session, args.file)
            print(f"Wrote {len(export_log(session)['places'])} logged places to {args.file}")
            return 0
        if not args.file.exists():
            print(f"No log at {args.file}")
            return 1
        try:
            data = json.loads(args.file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"{args.file}: line {e.lineno}, column {e.colno}: {e.msg}. Nothing restored.")
            return 1
        restored, unmatched = restore_log(session, data)
        print(f"Restored {restored} places.")
        for name in unmatched:
            print(f"  no matching place (import its reels first): {name}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
