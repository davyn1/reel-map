from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app import sync
from app.auth import require_user
from app.db import get_session
from app.schemas import VersionOut

router = APIRouter(prefix="/api", tags=["sync"], dependencies=[Depends(require_user)])


@router.get("/version", response_model=VersionOut)
def version(response: Response, session: Session = Depends(get_session)):
    """A number that goes up whenever shared data changes (app.sync). Open apps poll it and re-fetch
    only when it moved. Tiny on purpose: it's asked every few seconds while the map is on screen."""
    response.headers["Cache-Control"] = "no-store"
    return VersionOut(version=sync.current(session))
