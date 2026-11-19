from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# Extra spots for multi-spot reels. reels.place_id stays the reel's main (pinned) place.
reel_extra_places = Table(
    "reel_extra_places",
    Base.metadata,
    Column("reel_id", ForeignKey("reels.id"), primary_key=True),
    Column("place_id", ForeignKey("places.id"), primary_key=True),
)


class Trip(Base):
    """A map of its own: the Bay Area (the home trip, made automatically) or a trip somewhere else.
    Its area is a lat/lng box: pins must fall inside it, and the map opens on it."""

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True)  # for Muse's upload address: /api/import?trip=<slug>
    name: Mapped[str] = mapped_column(String)
    south: Mapped[float] = mapped_column(Float)
    west: Mapped[float] = mapped_column(Float)
    north: Mapped[float] = mapped_column(Float)
    east: Mapped[float] = mapped_column(Float)
    is_home: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    def contains(self, lat: float, lng: float) -> bool:
        return self.south <= lat <= self.north and self.west <= lng <= self.east


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int | None] = mapped_column(ForeignKey("trips.id"))
    name: Mapped[str] = mapped_column(String)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(String)
    is_approximate: Mapped[bool] = mapped_column(Boolean, default=False)
    # Tags you picked by hand; None means use the automatic ones (app.tags).
    tags_override: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    # Removed from the map by hand (e.g. unsaved on Instagram). Hidden, not deleted: its reels stay
    # linked so later imports skip them, and its log and tags are kept in case it's brought back.
    removed: Mapped[bool] = mapped_column(Boolean, default=False)

    trip: Mapped[Trip | None] = relationship()
    reels: Mapped[list["Reel"]] = relationship(back_populates="place")
    extra_reels: Mapped[list["Reel"]] = relationship(secondary=reel_extra_places, back_populates="extra_places")
    visits: Mapped[list["Visit"]] = relationship(back_populates="place")


class Reel(Base):
    __tablename__ = "reels"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_url: Mapped[str] = mapped_column(String, unique=True)
    posted_by: Mapped[str | None] = mapped_column(String)
    venue_raw: Mapped[str | None] = mapped_column(String)
    address_raw: Mapped[str | None] = mapped_column(String)
    city_raw: Mapped[str | None] = mapped_column(String)
    lat_raw: Mapped[float | None] = mapped_column(Float)
    lng_raw: Mapped[float | None] = mapped_column(Float)
    dish: Mapped[str | None] = mapped_column(Text)
    muse_confidence: Mapped[str | None] = mapped_column(String)
    muse_note: Mapped[str | None] = mapped_column(Text)
    place_id: Mapped[int | None] = mapped_column(ForeignKey("places.id"))
    status: Mapped[str] = mapped_column(String, default="needs_review")  # matched / needs_review / rejected
    flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    review_reason: Mapped[str | None] = mapped_column(Text)
    source_file: Mapped[str | None] = mapped_column(String)  # export file name, or "manual"
    added_by: Mapped[str | None] = mapped_column(String)  # username, for places added by hand in the app
    trip_id: Mapped[int | None] = mapped_column(ForeignKey("trips.id"))  # the trip it was imported into

    trip: Mapped[Trip | None] = relationship()
    place: Mapped[Place | None] = relationship(back_populates="reels")
    extra_places: Mapped[list[Place]] = relationship(secondary=reel_extra_places, back_populates="extra_reels")


class Visit(Base):
    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id"))
    user: Mapped[str] = mapped_column(String)  # users.username
    visited: Mapped[bool] = mapped_column(Boolean, default=False)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    visited_date: Mapped[date | None] = mapped_column(Date)
    rating: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    place: Mapped[Place] = relationship(back_populates="visits")

    __table_args__ = (UniqueConstraint("place_id", "user"),)


class User(Base):
    """You and your friend. Accounts are made with `python -m app.users`; there is no sign-up page."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String, unique=True)  # also the key in visits.user
    display_name: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    sessions: Mapped[list["LoginSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class LoginSession(Base):
    """A logged-in browser. Only a hash of the cookie's token is stored."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String, unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

    user: Mapped[User] = relationship(back_populates="sessions")


class ImportRun(Base):
    """One import: a Muse upload or a command-line run. Shown as "Last import: …" in the app."""

    __tablename__ = "import_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String)  # "upload" | "cli"
    filename: Mapped[str | None] = mapped_column(String)
    ok: Mapped[bool] = mapped_column(Boolean)
    error: Mapped[str | None] = mapped_column(Text)
    imported: Mapped[int] = mapped_column(Integer, default=0)
    pinned: Mapped[int] = mapped_column(Integer, default=0)
    approximate: Mapped[int] = mapped_column(Integer, default=0)
    needs_review: Mapped[int] = mapped_column(Integer, default=0)
    skipped: Mapped[int] = mapped_column(Integer, default=0)
    merged: Mapped[int] = mapped_column(Integer, default=0)


class AppState(Base):
    """One row (id 1): `version` goes up with every commit that changes shared data (app.sync), so open
    apps can ask "anything new?" cheaply and only re-fetch when it moved."""

    __tablename__ = "app_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    version: Mapped[int] = mapped_column(Integer, default=0)


class AlertSent(Base):
    """When each kind of Discord alert last went out, so a repeating problem doesn't spam (app.alerts)."""

    __tablename__ = "alerts_sent"

    kind: Mapped[str] = mapped_column(String, primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime)
