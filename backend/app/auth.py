"""Logins: password hashing, session cookies, and the "must be logged in" dependency.

- Passwords: scrypt (stdlib) with a random salt per user, stored as "scrypt$n$r$p$salt$hash".
- Sessions: a random token in an HttpOnly cookie; only its SHA-256 is stored, so a leaked
  database can't be used to log in. Sessions last SESSION_DAYS.
- Brute force: after MAX_FAILURES wrong passwords for a username, logins for it are refused
  for LOCKOUT_MINUTES (in memory; resets on restart, which is fine for two users).
"""

import base64
import hashlib
import hmac
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import LoginSession, User

COOKIE_NAME = "yums_session"
SESSION_DAYS = 60
MAX_FAILURES = 5
LOCKOUT_MINUTES = 15
# Secure cookies only travel over https. On by default for the hosted app; .env can turn it off
# for plain-http local use.
COOKIE_SECURE = os.getenv("FOOD_MAP_COOKIE_SECURE", "true").lower() not in ("0", "false", "no")

_SCRYPT = {"n": 2**15, "r": 8, "p": 1}


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, maxmem=64 * 1024 * 1024, dklen=32, **_SCRYPT)
    return f"scrypt${_SCRYPT['n']}${_SCRYPT['r']}${_SCRYPT['p']}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    candidate = hashlib.scrypt(
        password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p), maxmem=64 * 1024 * 1024, dklen=32
    )
    return hmac.compare_digest(candidate, _unb64(digest))


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(session: Session, user: User) -> str:
    """Start a login; returns the raw token for the cookie."""
    token = secrets.token_urlsafe(32)
    now = _now()
    session.add(LoginSession(token_hash=_token_hash(token), user=user, created_at=now, expires_at=now + timedelta(days=SESSION_DAYS)))
    session.commit()
    return token


def end_session(session: Session, token: str | None) -> None:
    if not token:
        return
    row = session.scalars(select(LoginSession).where(LoginSession.token_hash == _token_hash(token))).first()
    if row is not None:
        session.delete(row)
        session.commit()


def user_for_token(session: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = session.scalars(select(LoginSession).where(LoginSession.token_hash == _token_hash(token))).first()
    if row is None:
        return None
    if row.expires_at < _now():
        session.delete(row)
        session.commit()
        return None
    return row.user


def require_user(request: Request, session: Session = Depends(get_session)) -> User:
    """Dependency for every protected route: the logged-in user, or 401."""
    user = user_for_token(session, request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(401, "not logged in")
    return user


class LoginThrottle:
    """Counts wrong passwords per username; locks that username out for a while after too many."""

    def __init__(self, max_failures: int = MAX_FAILURES, lockout_seconds: int = LOCKOUT_MINUTES * 60):
        self.max_failures = max_failures
        self.lockout_seconds = lockout_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def locked_for(self, username: str) -> int:
        """Seconds left on a lockout, or 0."""
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._failures.get(username, []) if now - t < self.lockout_seconds]
            self._failures[username] = recent
            if len(recent) >= self.max_failures:
                return int(self.lockout_seconds - (now - recent[0])) + 1
            return 0

    def failed(self, username: str) -> None:
        with self._lock:
            self._failures.setdefault(username, []).append(time.monotonic())

    def succeeded(self, username: str) -> None:
        with self._lock:
            self._failures.pop(username, None)


throttle = LoginThrottle()
