from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ReelBrief(BaseModel):
    id: int
    post_url: str
    posted_by: str | None
    dish: str | None
    status: str


class PlaceOut(BaseModel):
    id: int
    name: str
    lat: float
    lng: float
    address: str | None
    city: str | None
    is_approximate: bool
    google_maps_url: str
    visited: bool
    visited_date: date | None
    reels: list[ReelBrief]


class StatsOut(BaseModel):
    reels_saved: int  # every reel that isn't rejected
    on_map: int  # places
    cities: int
    needs_review: int


class PlaceBrief(BaseModel):
    id: int
    name: str
    address: str | None
    is_approximate: bool


class ReviewReelOut(BaseModel):
    id: int
    post_url: str
    posted_by: str | None
    venue_raw: str | None
    address_raw: str | None
    city_raw: str | None
    lat_raw: float | None
    lng_raw: float | None
    dish: str | None
    muse_confidence: str | None
    muse_note: str | None
    status: str
    flags: list[str]
    review_reason: str | None
    place: PlaceBrief | None
    extra_places: list[PlaceBrief]


class VisitIn(BaseModel):
    visited: bool


class NewPlace(BaseModel):
    name: str = Field(min_length=1)
    lat: float
    lng: float
    address: str | None = None
    is_approximate: bool = False


class AttachPlaceIn(BaseModel):
    """Either an existing place_id or a new place. mode "replace" sets the reel's main place
    and resolves it; "add" links an extra spot (multi-spot reels) and leaves it in review."""

    place_id: int | None = None
    new_place: NewPlace | None = None
    mode: Literal["replace", "add"] = "replace"

    @model_validator(mode="after")
    def exactly_one(self):
        if (self.place_id is None) == (self.new_place is None):
            raise ValueError("give exactly one of place_id or new_place")
        return self
