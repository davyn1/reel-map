import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import demo
from app.db import get_session
from app.main import app
from app.models import Place, Reel, User, Visit
from app.routers.auth import throttle


@pytest.fixture
def demo_db(monkeypatch):
    """The demo, reset onto an in-memory database."""
    monkeypatch.setattr(demo, "DEMO", True)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    demo.reset(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield engine, Session
    app.dependency_overrides.clear()
    throttle.succeeded(demo.DEMO_USERNAME)


def demo_login() -> TestClient:
    c = TestClient(app)
    info = c.get("/api/demo").json()
    res = c.post("/api/auth/login", json={"username": info["username"], "password": info["password"]})
    assert res.status_code == 200, res.text
    return c


def test_sample_data_covers_every_feature(demo_db):
    _, Session = demo_db
    with Session() as s:
        places = s.scalars(select(Place)).all()
        assert len(places) >= 25
        assert any(p.is_approximate for p in places)
        assert s.scalar(select(func.count()).where(Reel.status == "needs_review")) == 3
        assert {u.username for u in s.scalars(select(User))} == {demo.DEMO_USERNAME, demo.FRIEND_USERNAME}
        assert s.scalar(select(func.count(Visit.id))) == len(demo._VISITS)

    c = demo_login()
    places = c.get("/api/places").json()
    assert any(p["others"] for p in places)  # friend mode has something to show
    assert any(p["visited"] and p["rating"] for p in places)
    tags = {t for p in places for t in p["tags"]}
    assert {"Korean", "Mexican", "Japanese", "Seafood"} <= tags


def test_reset_undoes_visitors_changes(demo_db):
    engine, Session = demo_db
    c = demo_login()
    c.post("/api/places", json={"name": "Graffiti", "lat": 37.8, "lng": -122.27}).raise_for_status()
    demo.reset(engine)
    with Session() as s:
        assert s.scalars(select(Place).where(Place.name == "Graffiti")).first() is None
    assert c.get("/api/places").status_code == 401  # logins don't survive a reset either


def test_demo_info_is_only_on_the_demo(monkeypatch):
    monkeypatch.setattr(demo, "DEMO", False)
    assert TestClient(app).get("/api/demo").status_code == 404


def test_demo_login_is_never_locked_out(demo_db):
    c = TestClient(app)
    for _ in range(10):
        assert c.post("/api/auth/login", json={"username": "demo", "password": "wrong"}).status_code == 401
    demo_login()


def test_uploads_are_off_in_the_demo(demo_db):
    res = demo_login().post("/api/import", content=json.dumps([]), headers={"Content-Type": "application/json"})
    assert res.status_code == 403
