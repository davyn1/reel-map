"""Your personal log as a small, readable JSON file: personal/my-log.json.

The database can be rebuilt from Muse exports, except what people added by hand: been-here,
visit dates, ratings, notes, favorites (per person) and hand-picked food tags (shared). That part
is written here after every change, so it can be kept and restored onto a fresh database.

Places are identified by their reels' post URLs (stable across re-imports), not database IDs.
Output is sorted and has no timestamps, so a diff shows only what changed.

Format (version 2):
    {"version": 2,
     "users": {"davy": {"places": [{"name", "post_urls", "visited"?, "visited_date"?, "rating"?,
                                    "notes"?, "favorite"?}, ...]}, ...},
     "tags":  [{"name", "post_urls", "tags": [...]}, ...]}
Version 1 (before logins: one person's entries, tags inline) still restores, into --user.

All personal data in the repo lives under personal/; see the README to remove it.

    python -m app.backup export                  # write personal/my-log.json from the database
    python -m app.backup restore                 # apply it to the database
    python -m app.backup restore --user davy     # a version-1 file: whose log it is
"""

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import PERSONAL_DIR
from app.models import Place, Reel, User, Visit

LOG_PATH = PERSONAL_DIR / "my-log.json"
VERSION = 2
LEGACY_USER = "me"  # visits.user before logins existed


def _post_urls(place: Place) -> list[str]:
    return sorted({r.post_url for r in [*place.reels, *place.extra_reels]})


def _visit_entry(place: Place, visit: Visit) -> dict | None:
    entry: dict = {"name": place.name, "post_urls": _post_urls(place)}
    if visit.visited:
        entry["visited"] = True
        if visit.visited_date:
            entry["visited_date"] = visit.visited_date.isoformat()
        if visit.rating:
            entry["rating"] = visit.rating
    if visit.notes:
        entry["notes"] = visit.notes
    if visit.favorite:
        entry["favorite"] = True
    return entry if len(entry) > 2 else None  # only name + post_urls: nothing logged


def _sort_key(e: dict) -> tuple[str, str]:
    return (e["name"].lower(), e["post_urls"][0])


def export_log(session: Session) -> dict:
    places = session.scalars(
        select(Place).options(selectinload(Place.reels), selectinload(Place.extra_reels), selectinload(Place.visits))
    ).all()
    users: dict[str, list[dict]] = {}
    tags: list[dict] = []
    for place in places:
        if not _post_urls(place):
            continue
        for visit in place.visits:
            if (entry := _visit_entry(place, visit)) is not None:
                users.setdefault(visit.user, []).append(entry)
        if place.tags_override is not None:
            tags.append({"name": place.name, "post_urls": _post_urls(place), "tags": place.tags_override})
    return {
        "version": VERSION,
        "users": {u: {"places": sorted(entries, key=_sort_key)} for u, entries in sorted(users.items())},
        "tags": sorted(tags, key=_sort_key),
    }


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


def _find_place(session: Session, post_urls: list[str]) -> Place | None:
    reel = session.scalars(select(Reel).where(Reel.post_url.in_(post_urls))).first()
    if reel is None:
        return None
    return reel.place or (reel.extra_places[0] if reel.extra_places else None)


def _apply_visit(session: Session, place: Place, username: str, entry: dict) -> None:
    visit = next((v for v in place.visits if v.user == username), None)
    if visit is None:
        visit = Visit(place=place, user=username)
        session.add(visit)
    visit.visited = bool(entry.get("visited"))
    visit.visited_date = date.fromisoformat(entry["visited_date"]) if entry.get("visited_date") else None
    visit.rating = entry.get("rating")
    visit.notes = entry.get("notes")
    visit.favorite = bool(entry.get("favorite"))


def _upgrade(data: dict, v1_user: str) -> dict:
    """Version 1 (single person, tags inline) -> version 2 layout."""
    if data.get("version", 1) >= 2:
        return data
    entries = data.get("places", [])
    return {
        "version": 2,
        "users": {v1_user: {"places": entries}},
        "tags": [{"name": e.get("name", "?"), "post_urls": e.get("post_urls", []), "tags": e["tags"]} for e in entries if "tags" in e],
    }


def restore_log(session: Session, data: dict, v1_user: str = LEGACY_USER) -> tuple[int, list[str]]:
    """Apply a log to the database. Returns (entries restored, names of entries with no matching place)."""
    data = _upgrade(data, v1_user)
    restored, unmatched = 0, []
    for username, section in data.get("users", {}).items():
        for entry in section.get("places", []):
            place = _find_place(session, entry.get("post_urls", []))
            if place is None:
                unmatched.append(entry.get("name", "?"))
                continue
            _apply_visit(session, place, username, entry)
            restored += 1
    for entry in data.get("tags", []):
        place = _find_place(session, entry.get("post_urls", []))
        if place is None:
            unmatched.append(entry.get("name", "?"))
            continue
        place.tags_override = entry.get("tags")
        restored += 1
    session.commit()
    return restored, unmatched


def main(argv=None) -> int:
    from app.db import SessionLocal, init_db

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["export", "restore"])
    parser.add_argument("--file", type=Path, default=LOG_PATH)
    parser.add_argument("--user", help="whose log a version-1 file is (default: the first account, else 'me')")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    init_db()
    with SessionLocal() as session:
        if args.action == "export":
            write_log(session, args.file)
            data = export_log(session)
            people = ", ".join(f"{u}: {len(s['places'])}" for u, s in data["users"].items()) or "nobody"
            print(f"Wrote {args.file} ({people}; {len(data['tags'])} hand-picked tag sets)")
            return 0
        if not args.file.exists():
            print(f"No log at {args.file}")
            return 1
        try:
            data = json.loads(args.file.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"{args.file}: line {e.lineno}, column {e.colno}: {e.msg}. Nothing restored.")
            return 1
        first = session.scalars(select(User).order_by(User.id)).first()
        v1_user = args.user or (first.username if first else LEGACY_USER)
        restored, unmatched = restore_log(session, data, v1_user)
        print(f"Restored {restored} entries.")
        for name in unmatched:
            print(f"  no matching place (import its reels first): {name}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
