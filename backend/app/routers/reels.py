from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app import backup
from app.db import get_session
from app.importer.flags import FLAG_DESCRIPTIONS, in_bay_area
from app.models import Place, Reel, Visit
from app.routers.places import place_city
from app.tags import TAG_ORDER
from app.schemas import AttachPlaceIn, PlaceBrief, ReviewReelOut, StatsOut

router = APIRouter(prefix="/api", tags=["reels"])


def brief(place: Place) -> PlaceBrief:
    return PlaceBrief(id=place.id, name=place.name, address=place.address, is_approximate=place.is_approximate)


def reel_out(reel: Reel) -> ReviewReelOut:
    return ReviewReelOut(
        id=reel.id,
        post_url=reel.post_url,
        posted_by=reel.posted_by,
        venue_raw=reel.venue_raw,
        address_raw=reel.address_raw,
        city_raw=reel.city_raw,
        lat_raw=reel.lat_raw,
        lng_raw=reel.lng_raw,
        dish=reel.dish,
        muse_confidence=reel.muse_confidence,
        muse_note=reel.muse_note,
        status=reel.status,
        flags=reel.flags or [],
        review_reason=reel.review_reason,
        place=brief(reel.place) if reel.place else None,
        extra_places=[brief(p) for p in reel.extra_places],
    )


def get_reel(session: Session, reel_id: int) -> Reel:
    reel = session.get(Reel, reel_id)
    if reel is None:
        raise HTTPException(404, "reel not found")
    return reel


def drop_if_orphaned(session: Session, place: Place | None) -> None:
    """A place with no reels left disappears from the map, unless you've logged it (visited, favorite or notes)."""
    if place is None:
        return
    session.flush()
    session.refresh(place)
    if place.reels or place.extra_reels or any(v.visited or v.favorite or v.notes for v in place.visits):
        return
    for visit in place.visits:
        session.delete(visit)
    session.delete(place)


@router.get("/stats", response_model=StatsOut)
def stats(session: Session = Depends(get_session)):
    places = session.scalars(select(Place).options(selectinload(Place.reels), selectinload(Place.extra_reels))).all()
    return StatsOut(
        reels_saved=session.scalar(select(func.count(Reel.id)).where(Reel.status != "rejected")),
        on_map=len(places),
        cities=len({c for p in places if (c := place_city(p))}),
        needs_review=session.scalar(select(func.count(Reel.id)).where(Reel.status == "needs_review")),
        visited=session.scalar(select(func.count(Visit.id)).where(Visit.visited.is_(True))),
        favorites=session.scalar(select(func.count(Visit.id)).where(Visit.favorite.is_(True))),
    )


@router.get("/tags")
def list_tags() -> list[str]:
    """Every food tag, in display order. Hand-picked tags must come from this list."""
    return TAG_ORDER


@router.get("/flags")
def list_flags() -> dict[str, str]:
    return FLAG_DESCRIPTIONS


@router.get("/reels/review", response_model=list[ReviewReelOut])
def review_queue(flag: str | None = Query(None), session: Session = Depends(get_session)):
    if flag is not None and flag not in FLAG_DESCRIPTIONS:
        raise HTTPException(422, f"unknown flag {flag!r}; known: {', '.join(FLAG_DESCRIPTIONS)}")
    reels = session.scalars(
        select(Reel)
        .where(Reel.status == "needs_review")
        .options(selectinload(Reel.place), selectinload(Reel.extra_places))
        .order_by(Reel.id)
    )
    return [reel_out(r) for r in reels if flag is None or flag in (r.flags or [])]


@router.post("/reels/{reel_id}/place", response_model=ReviewReelOut)
def attach_place(reel_id: int, body: AttachPlaceIn, session: Session = Depends(get_session)):
    reel = get_reel(session, reel_id)
    if body.place_id is not None:
        place = session.get(Place, body.place_id)
        if place is None:
            raise HTTPException(404, "place not found")
    else:
        new = body.new_place
        if not in_bay_area(new.lat, new.lng):
            raise HTTPException(422, "lat/lng is outside the Bay Area (swapped?)")
        place = Place(name=new.name.strip(), lat=new.lat, lng=new.lng, address=new.address, is_approximate=new.is_approximate)
        session.add(place)

    if body.mode == "add":
        if reel.place is None:
            raise HTTPException(409, "reel has no main place yet; use mode 'replace' first")
        if place is not reel.place and place not in reel.extra_places:
            reel.extra_places.append(place)
    else:
        previous = reel.place
        reel.place = place
        reel.status = "matched"
        reel.review_reason = None
        if previous is not place:
            drop_if_orphaned(session, previous)
    session.commit()
    backup.save_log_quietly(session)
    return reel_out(reel)


@router.post("/reels/{reel_id}/resolve", response_model=ReviewReelOut)
def resolve(reel_id: int, session: Session = Depends(get_session)):
    """Keep the reel's current place(s) and take it out of review (e.g. multi-spot reel, all spots added)."""
    reel = get_reel(session, reel_id)
    if reel.place is None:
        raise HTTPException(409, "reel has no place; attach one or reject it")
    reel.status = "matched"
    reel.review_reason = None
    session.commit()
    backup.save_log_quietly(session)
    return reel_out(reel)


@router.post("/reels/{reel_id}/reject", response_model=ReviewReelOut)
def reject(reel_id: int, session: Session = Depends(get_session)):
    reel = get_reel(session, reel_id)
    previous, extras = reel.place, list(reel.extra_places)
    reel.place = None
    reel.extra_places.clear()
    reel.status = "rejected"
    for place in [previous, *extras]:
        drop_if_orphaned(session, place)
    session.commit()
    backup.save_log_quietly(session)
    return reel_out(reel)
