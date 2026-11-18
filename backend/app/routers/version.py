import os
import re

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app import sync
from app.auth import require_user
from app.config import FRONTEND_DIST
from app.db import get_session
from app.schemas import VersionOut

router = APIRouter(prefix="/api", tags=["sync"], dependencies=[Depends(require_user)])

# The built map's main script, e.g. "assets/index-C9333xIF.js". Vite names it after its contents, so
# it changes with every build that changes the app: it's the build's identity.
DIST = FRONTEND_DIST
_BUILD_SCRIPT = re.compile(r"assets/index-[\w-]+\.js")
_cache: tuple[float, str | None] | None = None


def current_build() -> str | None:
    """The build the server hands out now, or None when no built map is served (local dev, tests).
    Re-read only when index.html changes, so polling it costs a stat, not a file read."""
    global _cache
    index = DIST / "index.html"
    try:
        mtime = os.stat(index).st_mtime
    except OSError:
        return None
    if _cache is None or _cache[0] != mtime:
        match = _BUILD_SCRIPT.search(index.read_text(encoding="utf-8"))
        _cache = (mtime, match.group(0) if match else None)
    return _cache[1]


@router.get("/version", response_model=VersionOut)
def version(response: Response, session: Session = Depends(get_session)):
    """A number that goes up whenever shared data changes (app.sync), and the app build being served.
    Open apps poll it: they re-fetch only when the number moved, and offer a reload when the build
    differs from the one they're running (an app resumed from the background after a deploy).
    Tiny on purpose: it's asked every few seconds while the map is on screen."""
    response.headers["Cache-Control"] = "no-store"
    return VersionOut(version=sync.current(session), build=current_build())
