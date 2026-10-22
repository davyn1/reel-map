import math
import re
import uuid
from collections import Counter
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import backup
from app.auth import require_user
from app.db import get_session
from app.maps_link import google_maps_url
from app.importer.flags import in_bay_area
from app.importer.matching import MIN_MERGE_NAME_SCORE, name_score
from app.importer.parse import normalize_post_url
from app.models import Place, Reel, User, Visit
from app.schemas import CreatePlaceIn, FriendVisitOut, PlaceOut, ReelBrief, TagsIn, VisitIn
from app.tags import TAG_ORDER, place_tags, sort_tags

router = APIRouter(prefix="/api/places", tags=["places"], dependencies=[Depends(require_user)])


_CITY_BEFORE_STATE = re.compile(r"([^,]+),\s*CA\b")


def place_city(place: Place) -> str | None:
    """Most common city among the place's reels, else the city in its address."""
    cities = Counter(r.city_raw for r in [*place.reels, *place.extra_reels] if r.city_raw)
    if cities:
        return cities.most_common(1)[0][0]
    match = _CITY_BEFORE_STATE.search(place.address or "")
    return match.group(1).strip() if match else None


def display_names(session: Session) -> dict[str, str]:
    return {u.username: u.display_name for u in session.scalars(select(User))}


def place_out(place: Place, me: str, names: dict[str, str]) -> PlaceOut:
    """`me` is the logged-in username: their visit fills the top-level fields, everyone else's goes in `others`."""
    visit = next((v for v in place.visits if v.user == me), None)
    others = [
        FriendVisitOut(username=v.user, display_name=names.get(v.user, v.user), visited=v.visited,
                       rating=v.rating, notes=v.notes, favorite=v.favorite)
        for v in sorted(place.visits, key=lambda v: v.user)
        if v.user != me and (v.visited or v.favorite or v.notes)
    ]
    reels = sorted({r.id: r for r in [*place.reels, *place.extra_reels] if r.status != "rejected"}.values(), key=lambda r: r.id)
    return PlaceOut(
        id=place.id,
        name=place.name,
        lat=place.lat,
        lng=place.lng,
        address=place.address,
        city=place_city(place),
        tags=place_tags(place),
        tags_edited=place.tags_override is not None,
        is_approximate=place.is_approximate,
        google_maps_url=google_maps_url(place.name, place.address, place.lat, place.lng),
        visited=bool(visit and visit.visited),
        visited_date=visit.visited_date if visit else None,
        rating=visit.rating if visit else None,
        notes=visit.notes if visit else None,
        favorite=bool(visit and visit.favorite),
        others=others,
        reels=[
            ReelBrief(id=r.id, post_url=r.post_url, posted_by=r.posted_by, dish=r.dish, status=r.status,
                      added_by=names.get(r.added_by, r.added_by) if r.added_by else None)
            for r in reels
        ],
    )


@router.get("", response_model=list[PlaceOut])
def list_places(user: User = Depends(require_user), session: Session = Depends(get_session)):
    places = session.scalars(
        select(Place)
        .options(selectinload(Place.reels), selectinload(Place.extra_reels), selectinload(Place.visits))
        .order_by(Place.id)  # import order; the map numbers pins in this order
    )
    names = display_names(session)
    return [place_out(p, user.username, names) for p in places]


NEARBY_METERS = 150  # a similar name this close is probably the same place


def _meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lng2 - lng1) / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def _link_key(link: str | None) -> str:
    """The reel row's post_url: an Instagram link in canonical form, another http(s) link as-is,
    or a unique "manual:" key when there's no link."""
    link = (link or "").strip()
    if not link:
        return f"manual:{uuid.uuid4().hex[:12]}"
    if not link.lower().startswith(("http://", "https://")):
        raise HTTPException(422, "The link must start with http:// or https://")
    return normalize_post_url(link)


@router.post("", response_model=PlaceOut, status_code=201)
def create_place(body: CreatePlaceIn, user: User = Depends(require_user), session: Session = Depends(get_session)):
    """Add a place by hand. It gets a "manual" reel (holding the link, if any) so it behaves like any
    other place: shared with the other person, backed up, and recognized if Muse later exports the
    same reel. 409 if the link is already on the map, or (unless force) a similar place is nearby."""
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Give the place a name.")
    if not in_bay_area(body.lat, body.lng):
        raise HTTPException(422, "That pin is outside the Bay Area (are lat and lng swapped?)")
    if body.tags is not None:
        unknown = sorted(set(body.tags) - set(TAG_ORDER))
        if unknown:
            raise HTTPException(422, f"unknown tag(s): {', '.join(unknown)}")

    key = _link_key(body.link)
    existing = session.scalars(select(Reel).where(Reel.post_url == key)).first()
    if existing is not None:
        on = existing.place or (existing.extra_places[0] if existing.extra_places else None)
        raise HTTPException(409, {"message": f"That link is already on the map as {on.name}." if on else
                                  "That reel is already imported (it's in the review queue).",
                                  "place_id": on.id if on else None, "kind": "same_link"})
    if not body.force:
        for other in session.scalars(select(Place).where(Place.is_approximate.is_(False))):
            if _meters(body.lat, body.lng, other.lat, other.lng) <= NEARBY_METERS and name_score(name, other.name) >= MIN_MERGE_NAME_SCORE:
                raise HTTPException(409, {"message": f"{other.name} is already on the map right there. Add anyway?",
                                          "place_id": other.id, "kind": "similar_nearby"})

    place = Place(name=name, lat=body.lat, lng=body.lng, address=(body.address or "").strip() or None,
                  is_approximate=body.is_approximate, tags_override=sort_tags(body.tags) if body.tags is not None else None)
    session.add(place)
    session.add(Reel(post_url=key, venue_raw=name, address_raw=place.address, lat_raw=body.lat, lng_raw=body.lng,
                     place=place, status="matched", flags=[], source_file="manual", added_by=user.username))
    notes = (body.notes or "").strip() or None
    if body.favorite or body.visited or notes:
        session.add(Visit(place=place, user=user.username, favorite=body.favorite, visited=body.visited,
                          visited_date=date.today() if body.visited else None, notes=notes))
    session.commit()
    backup.save_log_quietly(session)
    session.refresh(place)
    return place_out(place, user.username, display_names(session))


@router.post("/{place_id}/visit", response_model=PlaceOut)
def update_visit(place_id: int, body: VisitIn, user: User = Depends(require_user), session: Session = Depends(get_session)):
    """Update the visit log. Only fields present in the body change; send null to clear rating/notes/date.

    `visited` takes the desired state rather than flipping, so a double click can't undo itself.
    Turning it on stamps today's date unless one is given; turning it off clears date and rating
    but keeps notes and favorite.
    """
    place = session.get(Place, place_id)
    if place is None:
        raise HTTPException(404, "place not found")
    visit = next((v for v in place.visits if v.user == user.username), None)
    if visit is None:
        visit = Visit(place=place, user=user.username)
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
    backup.save_log_quietly(session)
    return place_out(place, user.username, display_names(session))


@router.put("/{place_id}/tags", response_model=PlaceOut)
def set_tags(place_id: int, body: TagsIn, user: User = Depends(require_user), session: Session = Depends(get_session)):
    """Pick a place's tags by hand (any of GET /api/tags, or none), or send null to go back to automatic."""
    place = session.get(Place, place_id)
    if place is None:
        raise HTTPException(404, "place not found")
    if body.tags is not None:
        unknown = sorted(set(body.tags) - set(TAG_ORDER))
        if unknown:
            raise HTTPException(422, f"unknown tag(s): {', '.join(unknown)}; choose from GET /api/tags")
        place.tags_override = sort_tags(body.tags)
    else:
        place.tags_override = None
    session.commit()
    backup.save_log_quietly(session)
    return place_out(place, user.username, display_names(session))
