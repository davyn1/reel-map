from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import backup, trips
from app.auth import require_user
from app.db import get_session
from app.models import Place, Reel, Trip
from app.schemas import TripIn, TripOut, TripRenameIn

router = APIRouter(prefix="/api/trips", tags=["trips"], dependencies=[Depends(require_user)])


def trip_out(session: Session, trip: Trip) -> TripOut:
    count = session.scalar(select(func.count(Place.id)).where(Place.trip_id == trip.id, Place.removed.is_(False)))
    return TripOut(id=trip.id, slug=trip.slug, name=trip.name, is_home=trip.is_home, south=trip.south,
                   west=trip.west, north=trip.north, east=trip.east, places=count or 0)


def get_trip(session: Session, trip_id: int) -> Trip:
    trip = session.get(Trip, trip_id)
    if trip is None:
        raise HTTPException(404, "trip not found")
    return trip


@router.get("", response_model=list[TripOut])
def list_trips(session: Session = Depends(get_session)):
    """The Bay Area first, then the other trips, newest first."""
    rows = session.scalars(select(Trip).order_by(Trip.is_home.desc(), Trip.created_at.desc(), Trip.id.desc()))
    return [trip_out(session, t) for t in rows]


@router.post("", response_model=TripOut, status_code=201)
def create_trip(body: TripIn, session: Session = Depends(get_session)):
    """A new trip: a name and the area it covers (the app finds it by searching for a city).
    Its slug, for Muse's upload address, comes from the name and never changes."""
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Give the trip a name.")
    if (problem := trips.check_box(body.south, body.west, body.north, body.east)) is not None:
        raise HTTPException(422, problem)
    if session.scalars(select(Trip).where(func.lower(Trip.name) == name.lower())).first() is not None:
        raise HTTPException(409, f"There's already a trip called {name}.")
    trip = Trip(slug=trips.unique_slug(session, name), name=name, south=body.south, west=body.west,
                north=body.north, east=body.east, is_home=False,
                created_at=datetime.now(timezone.utc).replace(tzinfo=None))
    session.add(trip)
    session.commit()
    backup.save_log_quietly(session)
    return trip_out(session, trip)


@router.patch("/{trip_id}", response_model=TripOut)
def rename_trip(trip_id: int, body: TripRenameIn, session: Session = Depends(get_session)):
    """Rename a trip. Its slug (Muse's upload address) stays the same."""
    trip = get_trip(session, trip_id)
    name = body.name.strip()
    taken = session.scalars(select(Trip).where(func.lower(Trip.name) == name.lower(), Trip.id != trip.id)).first()
    if taken is not None:
        raise HTTPException(409, f"There's already a trip called {name}.")
    trip.name = name
    session.commit()
    backup.save_log_quietly(session)
    return trip_out(session, trip)


@router.delete("/{trip_id}", status_code=204)
def delete_trip(trip_id: int, session: Session = Depends(get_session)):
    """Delete a trip with nothing in it (a typo, a trip that didn't happen). A trip with places or
    imported reels can't be deleted: that would lose their logs. The Bay Area can't be deleted."""
    trip = get_trip(session, trip_id)
    if trip.is_home:
        raise HTTPException(409, "The Bay Area map can't be deleted.")
    has_places = session.scalar(select(func.count(Place.id)).where(Place.trip_id == trip.id))
    has_reels = session.scalar(select(func.count(Reel.id)).where(Reel.trip_id == trip.id))
    if has_places or has_reels:
        raise HTTPException(409, "Only an empty trip can be deleted.")
    session.delete(trip)
    session.commit()
    backup.save_log_quietly(session)
