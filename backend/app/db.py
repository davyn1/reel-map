from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import DATABASE_URL


class Base(DeclarativeBase):
    pass


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(bind=engine) -> None:
    from app import models  # noqa: F401  (registers tables)

    Base.metadata.create_all(bind)


def get_session():
    with SessionLocal() as session:
        yield session
