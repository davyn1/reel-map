"""Import Muse exports into the database.

    python -m app.importer.run [file] [--trip SLUG]

With no file, imports every data/reels*.json into the Bay Area (home) trip, and every
data/trips/<slug>/reels*.json into that trip (trips that exist; restore the backup first after
starting over). A file given by hand goes into --trip, or home. Reels whose post_url is already in
the database are skipped, so re-running only adds new reels. Pins use Muse's own coordinates;
nothing calls an external API.
"""

import argparse
from datetime import datetime, timezone
import sys
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import trips
from app.config import DATA_DIR
from app.db import SessionLocal, init_db
from app.importer.flags import FLAG_DESCRIPTIONS, compute_flags
from app.importer.matching import (
    MIN_MERGE_NAME_SCORE,
    display_address,
    display_name,
    name_score,
    normalize_address,
    normalize_name,
)
from app.importer.parse import ExportParseError, RawReel, find_export_files, load_file
from app.models import ImportRun, Place, Reel, Trip

# Flags that mean the row can't be put on the map at all.
BLOCKING_FLAGS = ("no_venue", "no_coords", "coords_outside_area", "coords_outside_bay_area", "no_confidence")


@dataclass
class Summary:
    imported: int = 0
    pinned: int = 0
    approximate: int = 0
    needs_review: int = 0
    pinned_needing_review: int = 0
    skipped: int = 0
    merged: int = 0
    flags: Counter = field(default_factory=Counter)
    skipped_details: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "imported": self.imported, "pinned": self.pinned, "approximate": self.approximate,
            "needs_review": self.needs_review, "pinned_needing_review": self.pinned_needing_review,
            "skipped": self.skipped, "merged": self.merged, "flags": dict(self.flags),
            "skipped_details": self.skipped_details,
        }

    def print(self) -> None:
        print(f"imported:      {self.imported}")
        print(f"  pinned:       {self.pinned}")
        print(f"  approximate:  {self.approximate}")
        print(f"  needs review: {self.needs_review} ({self.pinned_needing_review} of these are on the map, e.g. multi-spot reels)")
        print(f"skipped:       {self.skipped}")
        print(f"merged into existing places: {self.merged}")
        if self.flags:
            print("flags:")
            for flag in FLAG_DESCRIPTIONS:
                if self.flags[flag]:
                    print(f"  {flag}: {self.flags[flag]}")
        for line in self.skipped_details:
            print(f"  skipped {line}")


@dataclass
class Decision:
    place: Place | None
    status: str
    reason: str | None = None
    merged: bool = False


class Importer:
    def __init__(self, session: Session, trip: Trip):
        self.session = session
        self.trip = trip
        self.summary = Summary()

    def import_reel(self, raw: RawReel) -> None:
        flags = compute_flags(raw, self.trip.contains)
        decision = self._decide(raw, flags)
        if "multi_spot" in flags and decision.status == "matched":
            decision.status = "needs_review"
            decision.reason = "reel covers several spots; add the others"

        self.session.add(
            Reel(
                post_url=raw.post_url,
                posted_by=raw.posted_by,
                venue_raw=raw.venue,
                address_raw=raw.address,
                city_raw=raw.city,
                lat_raw=raw.lat,
                lng_raw=raw.lng,
                dish=raw.dish,
                muse_confidence=raw.confidence,
                muse_note=raw.note,
                place=decision.place,
                status=decision.status,
                flags=flags,
                review_reason=decision.reason,
                source_file=raw.source_file,
                trip=self.trip,
            )
        )
        self.session.flush()

        s = self.summary
        s.imported += 1
        s.flags.update(flags)
        s.merged += decision.merged
        # Exclusive buckets, so pinned + approximate + needs_review == imported.
        if decision.status == "needs_review":
            s.needs_review += 1
            s.pinned_needing_review += decision.place is not None
        elif decision.place.is_approximate:
            s.approximate += 1
        else:
            s.pinned += 1

    def _decide(self, raw: RawReel, flags: list[str]) -> Decision:
        blocking = [f for f in BLOCKING_FLAGS if f in flags]
        if blocking:
            return Decision(None, "needs_review", "; ".join(FLAG_DESCRIPTIONS[f] for f in blocking))
        if raw.confidence == "none":
            return Decision(None, "needs_review", "Muse confidence is none")
        # Low confidence (pop-ups, home cooks) or a city-only address: the pin is a guess.
        if raw.confidence == "low" or "city_only_address" in flags:
            return self._approximate_place(raw)
        return self._exact_place(raw)

    def _approximate_place(self, raw: RawReel) -> Decision:
        """Same pop-up in the same city shares a place; different pop-ups pinned to one city don't."""
        key = normalize_name(raw.venue)
        city = (raw.city or "").lower()
        for place in self.session.scalars(select(Place).where(Place.is_approximate.is_(True), Place.trip_id == self.trip.id)):
            same_city = any((r.city_raw or "").lower() == city for r in place.reels)
            if normalize_name(place.name) == key and same_city:
                return Decision(place, "matched", merged=True)
        return self._new_place(raw, is_approximate=True)

    def _exact_place(self, raw: RawReel) -> Decision:
        """Same street address AND a similar name. Name alone is never enough (spellings vary),
        and address alone isn't either (food halls and malls share addresses)."""
        key = normalize_address(raw.address)
        if key:
            for place in self.session.scalars(select(Place).where(Place.is_approximate.is_(False), Place.trip_id == self.trip.id)):
                if normalize_address(place.address) == key and name_score(place.name, raw.venue) >= MIN_MERGE_NAME_SCORE:
                    return Decision(place, "matched", merged=True)
        return self._new_place(raw, is_approximate=False)

    def _new_place(self, raw: RawReel, is_approximate: bool) -> Decision:
        place = Place(
            name=display_name(raw.venue),
            lat=raw.lat,
            lng=raw.lng,
            address=display_address(raw.address),
            is_approximate=is_approximate,
            trip=self.trip,
        )
        self.session.add(place)
        return Decision(place, "matched")


def run(paths, session: Session, trip: Trip | None = None) -> Summary:
    """Import into `trip` (default: the home trip). Parse every file first, so a bad file aborts
    before anything is written. Places only merge with places in the same trip."""
    parsed_files = [load_file(p) for p in paths]
    importer = Importer(session, trip or trips.home(session))
    known = set(session.scalars(select(Reel.post_url)))
    for parsed in parsed_files:
        for index, reason in parsed.skipped:
            importer.summary.skipped += 1
            importer.summary.skipped_details.append(f"{parsed.path.name} item {index}: {reason}")
        for raw in parsed.reels:
            if raw.post_url in known:
                importer.summary.skipped += 1
                continue
            known.add(raw.post_url)
            importer.import_reel(raw)
    session.commit()
    return importer.summary


def record_run(session: Session, source: str, filename: str | None, summary: Summary | None = None,
               error: str | None = None) -> ImportRun:
    run_row = ImportRun(created_at=datetime.now(timezone.utc).replace(tzinfo=None), source=source, filename=filename,
                        ok=error is None, error=error)
    if summary is not None:
        for key in ("imported", "pinned", "approximate", "needs_review", "skipped", "merged"):
            setattr(run_row, key, getattr(summary, key))
    session.add(run_row)
    session.commit()
    return run_row


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", nargs="?", help="one export file (default: every data/reels*.json, and data/trips/<slug>/)")
    parser.add_argument("--trip", help="the trip a file given by hand goes into (its slug; default: the Bay Area)")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252

    init_db()
    with SessionLocal() as session:
        if args.file:
            trip = trips.by_slug(session, args.trip) if args.trip else trips.home(session)
            if trip is None:
                print(f"No trip {args.trip!r}. Make it in the app first.")
                return 1
            batches = [(trip, find_export_files(args.file))]
        else:
            batches = [(trips.home(session), find_export_files())]
            trip_dir = DATA_DIR / "trips"
            for folder in sorted(trip_dir.glob("*")) if trip_dir.is_dir() else []:
                trip = trips.by_slug(session, folder.name)
                if trip is None:
                    print(f"Skipping data/trips/{folder.name}: no such trip (restore the backup first).")
                    continue
                batches.append((trip, sorted(folder.glob("reels*.json"))))
        batches = [(t, paths) for t, paths in batches if paths]
        if not batches:
            print("No export files found (looked for data/reels*.json and data/trips/<slug>/reels*.json).")
            return 1
        for trip, paths in batches:
            names = ", ".join(p.name for p in paths)
            try:
                summary = run(paths, session, trip)
            except ExportParseError as e:
                record_run(session, "cli", names, error=str(e))
                print(f"PARSE ERROR {e}")
                print(f"Nothing was imported into {trip.name}.")
                return 1
            record_run(session, "cli", names if trip.is_home else f"{names} ({trip.name})", summary)
            print(f"Imported into {trip.name} from {names}")
            summary.print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
