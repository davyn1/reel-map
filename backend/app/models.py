from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

REEL_STATUSES = ("matched", "needs_review", "rejected")

# Extra spots for multi-spot reels. reels.place_id stays the reel's main (pinned) place.
reel_extra_places = Table(
    "reel_extra_places",
    Base.metadata,
    Column("reel_id", ForeignKey("reels.id"), primary_key=True),
    Column("place_id", ForeignKey("places.id"), primary_key=True),
)


class Place(Base):
    __tablename__ = "places"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    address: Mapped[str | None] = mapped_column(String)
    is_approximate: Mapped[bool] = mapped_column(Boolean, default=False)
    # Tags you picked by hand; None means use the automatic ones (app.tags).
    tags_override: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

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
    status: Mapped[str] = mapped_column(String, default="needs_review")
    flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    review_reason: Mapped[str | None] = mapped_column(Text)
    source_file: Mapped[str | None] = mapped_column(String)  # export file name, or "manual"
    added_by: Mapped[str | None] = mapped_column(String)  # username, for places added by hand in the app

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
