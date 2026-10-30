from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import COOKIE_NAME, COOKIE_SECURE, SESSION_DAYS, create_session, end_session, require_user, throttle, verify_password
from app import demo
from app.db import get_session
from app.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str = ""  # may be left out when the server has a single account (passcode login)
    password: str


class ModeOut(BaseModel):
    passcode: bool


class MeOut(BaseModel):
    username: str
    display_name: str


def _only_user(session: Session) -> User | None:
    """The single account, when there's exactly one (and this isn't the demo, which has two)."""
    users = session.scalars(select(User).limit(2)).all()
    return users[0] if len(users) == 1 and not demo.DEMO else None


@router.get("/mode", response_model=ModeOut)
def mode(session: Session = Depends(get_session)):
    """Public: with a single account, the login screen asks only for its password (the passcode)."""
    return ModeOut(passcode=_only_user(session) is not None)


@router.post("/login", response_model=MeOut)
def login(body: LoginIn, response: Response, session: Session = Depends(get_session)):
    username = body.username.strip().lower()
    passcode = not username
    if passcode:
        only = _only_user(session)
        if only is None:
            raise HTTPException(422, "Enter a username.")
        username = only.username
    # The demo login is public; a lockout would only let one visitor lock everyone else out.
    guarded = not (demo.DEMO and username in (demo.DEMO_USERNAME, demo.FRIEND_USERNAME))
    wait = guarded and throttle.locked_for(username)
    if wait:
        raise HTTPException(429, f"Too many wrong passwords. Try again in {max(1, wait // 60)} min.")
    user = session.scalars(select(User).where(func.lower(User.username) == username)).first()
    if user is None or not verify_password(body.password, user.password_hash):
        if guarded:
            throttle.failed(username)
        raise HTTPException(401, "Wrong passcode." if passcode else "Wrong username or password.")
    throttle.succeeded(username)
    token = create_session(session, user)
    response.set_cookie(
        COOKIE_NAME, token, max_age=SESSION_DAYS * 86400, httponly=True, secure=COOKIE_SECURE, samesite="lax", path="/"
    )
    return MeOut(username=user.username, display_name=user.display_name)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session: Session = Depends(get_session)):
    end_session(session, request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(require_user)):
    return MeOut(username=user.username, display_name=user.display_name)
