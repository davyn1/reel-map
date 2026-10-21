from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ReelBrief(BaseModel):
    id: int
    post_url: str
    posted_by: str | None
    dish: str | None
    status: str


class FriendVisitOut(BaseModel):
    """Someone else's log for a place (friend mode). Only people who logged something appear."""

    username: str
    display_name: str
    visited: bool
    rating: int | None
    notes: str | None
    favorite: bool


class PlaceOut(BaseModel):
    id: int
    name: str
    lat: float
    lng: float
    address: str | None
    city: str | None
    is_approximate: bool
    google_maps_url: str
    tags: list[str]
    tags_edited: bool  # tags were picked by hand rather than worked out from captions
    visited: bool
    visited_date: date | None
    rating: int | None
    notes: str | None
    favorite: bool
    others: list[FriendVisitOut]
    reels: list[ReelBrief]


class StatsOut(BaseModel):
    reels_saved: int  # every reel that isn't rejected
    on_map: int  # places
    cities: int
    needs_review: int
    visited: int
    favorites: int


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


class TagsIn(BaseModel):
    """Tags to show for a place, from GET /api/tags. null goes back to automatic tags."""

    tags: list[str] | None


class VisitIn(BaseModel):
    """Partial update of the place's visit log: send only the fields that change."""

    visited: bool | None = None
    visited_date: date | None = None
    rating: int | None = Field(None, ge=1, le=5)
    notes: str | None = Field(None, max_length=2000)
    favorite: bool | None = None


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
