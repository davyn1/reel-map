import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_session, init_db
from app.main import app
from app.routers.auth import throttle
from app.users import add_user

PASSCODE = "shared-passcode"


@pytest.fixture
def one_account():
    """A server with a single (shared) account, like the real map."""
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    init_db(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as s:
        add_user(s, "bigbacking", "BIGBACKING", PASSCODE)

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield Session
    app.dependency_overrides.clear()
    throttle.succeeded("bigbacking")


def test_one_account_logs_in_with_just_the_passcode(one_account):
    c = TestClient(app)
    assert c.get("/api/auth/mode").json() == {"passcode": True}
    res = c.post("/api/auth/login", json={"password": PASSCODE})
    assert res.status_code == 200 and res.json()["username"] == "bigbacking"
    assert c.get("/api/places").status_code == 200


def test_wrong_passcode(one_account):
    res = TestClient(app).post("/api/auth/login", json={"password": "nope-nope-nope"})
    assert res.status_code == 401 and res.json()["detail"] == "Wrong passcode."


def test_wrong_passcodes_lock_the_account(one_account):
    c = TestClient(app)
    for _ in range(5):
        assert c.post("/api/auth/login", json={"password": "wrong"}).status_code == 401
    assert c.post("/api/auth/login", json={"password": PASSCODE}).status_code == 429


def test_username_login_still_works(one_account):
    res = TestClient(app).post("/api/auth/login", json={"username": "BigBacking", "password": PASSCODE})
    assert res.status_code == 200


def test_two_accounts_need_a_username(one_account):
    with one_account() as s:
        add_user(s, "friend", "Friend", "friend-password")
    c = TestClient(app)
    assert c.get("/api/auth/mode").json() == {"passcode": False}
    assert c.post("/api/auth/login", json={"password": PASSCODE}).status_code == 422


def test_no_accounts_is_not_passcode_mode(one_account):
    with one_account() as s:
        from app.models import User

        for u in s.query(User).all():
            s.delete(u)
        s.commit()
    assert TestClient(app).get("/api/auth/mode").json() == {"passcode": False}
