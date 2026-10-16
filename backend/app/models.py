from datetime import date

from sqlalchemy import JSON, Boolean, Column, Date, Float, ForeignKey, Integer, String, Table, Text, UniqueConstraint
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
    source_file: Mapped[str | None] = mapped_column(String)

    place: Mapped[Place | None] = relationship(back_populates="reels")
    extra_places: Mapped[list[Place]] = relationship(secondary=reel_extra_places, back_populates="extra_reels")


class Visit(Base):
    __tablename__ = "visits"

    id: Mapped[int] = mapped_column(primary_key=True)
    place_id: Mapped[int] = mapped_column(ForeignKey("places.id"))
    user: Mapped[str] = mapped_column(String, default="me")
    visited: Mapped[bool] = mapped_column(Boolean, default=False)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    visited_date: Mapped[date | None] = mapped_column(Date)
    rating: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)

    place: Mapped[Place] = relationship(back_populates="visits")

    __table_args__ = (UniqueConstraint("place_id", "user"),)
