import re
from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.maps_link import google_maps_url
from app.models import Place, Visit
from app.schemas import PlaceOut, ReelBrief, VisitIn
from app.tags import place_tags

router = APIRouter(prefix="/api/places", tags=["places"])

USER = "me"  # single user until auth exists


_CITY_BEFORE_STATE = re.compile(r"([^,]+),\s*CA\b")


def place_city(place: Place) -> str | None:
    """Most common city among the place's reels, else the city in its address."""
    cities = Counter(r.city_raw for r in [*place.reels, *place.extra_reels] if r.city_raw)
    if cities:
        return cities.most_common(1)[0][0]
    match = _CITY_BEFORE_STATE.search(place.address or "")
    return match.group(1).strip() if match else None


def place_out(place: Place) -> PlaceOut:
    visit = next((v for v in place.visits if v.user == USER), None)
    reels = sorted({r.id: r for r in [*place.reels, *place.extra_reels] if r.status != "rejected"}.values(), key=lambda r: r.id)
    return PlaceOut(
        id=place.id,
        name=place.name,
        lat=place.lat,
        lng=place.lng,
        address=place.address,
        city=place_city(place),
        tags=place_tags(place),
        is_approximate=place.is_approximate,
        google_maps_url=google_maps_url(place.name, place.address, place.lat, place.lng),
        visited=bool(visit and visit.visited),
        visited_date=visit.visited_date if visit else None,
        rating=visit.rating if visit else None,
        notes=visit.notes if visit else None,
        favorite=bool(visit and visit.favorite),
        reels=[ReelBrief(id=r.id, post_url=r.post_url, posted_by=r.posted_by, dish=r.dish, status=r.status) for r in reels],
    )


@router.get("", response_model=list[PlaceOut])
def list_places(session: Session = Depends(get_session)):
    places = session.scalars(
        select(Place)
        .options(selectinload(Place.reels), selectinload(Place.extra_reels), selectinload(Place.visits))
        .order_by(Place.id)  # import order; the map numbers pins in this order
    )
    return [place_out(p) for p in places]


@router.post("/{place_id}/visit", response_model=PlaceOut)
def update_visit(place_id: int, body: VisitIn, session: Session = Depends(get_session)):
    """Update the visit log. Only fields present in the body change; send null to clear rating/notes/date.

    `visited` takes the desired state rather than flipping, so a double click can't undo itself.
    Turning it on stamps today's date unless one is given; turning it off clears date and rating
    but keeps notes and favorite.
    """
    place = session.get(Place, place_id)
    if place is None:
        raise HTTPException(404, "place not found")
    visit = next((v for v in place.visits if v.user == USER), None)
    if visit is None:
        visit = Visit(place=place, user=USER)
        session.add(visit)
    sent = body.model_fields_set
    if "visited" in sent and body.visited is not None:
        if body.visited and not visit.visited:
            visit.visited_date = date.today()
        elif not body.visited:
            visit.visited_date = None
            visit.rating = None
        visit.visited = body.visited
    if "visited_date" in sent:
        visit.visited_date = body.visited_date
    if "rating" in sent:
        visit.rating = body.rating
    if "notes" in sent:
        visit.notes = (body.notes or "").strip() or None
    if "favorite" in sent and body.favorite is not None:
        visit.favorite = body.favorite
    session.commit()
    return place_out(place)
