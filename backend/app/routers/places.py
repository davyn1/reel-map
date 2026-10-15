from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.maps_link import google_maps_url
from app.models import Place, Visit
from app.schemas import PlaceOut, ReelBrief, VisitIn

router = APIRouter(prefix="/api/places", tags=["places"])

USER = "me"  # single user until auth exists


def place_out(place: Place) -> PlaceOut:
    visit = next((v for v in place.visits if v.user == USER), None)
    reels = sorted({r.id: r for r in [*place.reels, *place.extra_reels] if r.status != "rejected"}.values(), key=lambda r: r.id)
    return PlaceOut(
        id=place.id,
        name=place.name,
        lat=place.lat,
        lng=place.lng,
        address=place.address,
        is_approximate=place.is_approximate,
        google_maps_url=google_maps_url(place.name, place.address, place.lat, place.lng),
        visited=bool(visit and visit.visited),
        visited_date=visit.visited_date if visit else None,
        reels=[ReelBrief(id=r.id, post_url=r.post_url, posted_by=r.posted_by, dish=r.dish, status=r.status) for r in reels],
    )


@router.get("", response_model=list[PlaceOut])
def list_places(session: Session = Depends(get_session)):
    places = session.scalars(
        select(Place)
        .options(selectinload(Place.reels), selectinload(Place.extra_reels), selectinload(Place.visits))
        .order_by(Place.name)
    )
    return [place_out(p) for p in places]


@router.post("/{place_id}/visit", response_model=PlaceOut)
def set_visited(place_id: int, body: VisitIn, session: Session = Depends(get_session)):
    """Set "been here". Takes the desired state rather than flipping, so a double click can't undo itself."""
    place = session.get(Place, place_id)
    if place is None:
        raise HTTPException(404, "place not found")
    visit = next((v for v in place.visits if v.user == USER), None)
    if visit is None:
        visit = Visit(place=place, user=USER)
        session.add(visit)
    if body.visited and not visit.visited:
        visit.visited_date = date.today()
    elif not body.visited:
        visit.visited_date = None
    visit.visited = body.visited
    session.commit()
    return place_out(place)
