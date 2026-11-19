from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(bind=engine) -> None:
    from app import models, sync  # noqa: F401  (registers tables, and the live-sync change hook)

    from app.trips import ensure_home

    Base.metadata.create_all(bind)
    _add_missing_columns(bind)
    with bind.begin() as conn:
        ensure_home(conn)  # the Bay Area trip, and everything from before trips existed goes in it


# create_all only creates missing tables. Columns added to existing tables later are listed
# here and added in place, so an existing food_map.db keeps its data.
_ADDED_COLUMNS = {
    "visits": {"favorite": "BOOLEAN NOT NULL DEFAULT 0"},
    "places": {"tags_override": "JSON", "removed": "BOOLEAN NOT NULL DEFAULT 0", "trip_id": "INTEGER REFERENCES trips(id)"},
    "reels": {"added_by": "VARCHAR", "trip_id": "INTEGER REFERENCES trips(id)"},
}


def _add_missing_columns(bind) -> None:
    inspector = inspect(bind)
    with bind.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def get_session():
    with SessionLocal() as session:
        yield session
