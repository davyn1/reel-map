"""Muse uploads its export here; the app imports it. Also lists recent imports for the app.

    curl -X POST https://<app>/api/import \
         -H "Authorization: Bearer $FOOD_MAP_IMPORT_TOKEN" \
         -H "Content-Type: application/json" \
         --data-binary @reels.json

Who may upload: whoever sends the secret token from FOOD_MAP_IMPORT_TOKEN (Muse), or a
logged-in person. With no token configured, token uploads are switched off.

Every upload is saved first, as data/reels-upload-<UTC time>-<random>.json (the server's own history
of exports), then imported exactly like `python -m app.importer.run`: reels already seen are
skipped. A file that isn't valid JSON is kept as .invalid and the reply says where it broke.
"""

import hmac
import os
import secrets
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import backup, demo
from app.auth import COOKIE_NAME, require_user, user_for_token
from app.config import DATA_DIR
from app.db import get_session
from app.importer.parse import ExportParseError
from app.importer.run import record_run, run
from app.models import ImportRun

router = APIRouter(prefix="/api", tags=["imports"])

MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # a full export of hundreds of reels is well under 1 MB
_one_at_a_time = threading.Lock()


def import_token() -> str:
    return os.getenv("FOOD_MAP_IMPORT_TOKEN", "")


def allow_upload(request: Request, session: Session = Depends(get_session)) -> str:
    """The upload's source: "muse" for a valid token, the username for a logged-in person, else 401/503."""
    if demo.DEMO:
        raise HTTPException(403, "Uploads are off in the demo.")
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        expected = import_token()
        if not expected:
            raise HTTPException(503, "Uploads by token aren't set up on this server (FOOD_MAP_IMPORT_TOKEN).")
        if hmac.compare_digest(header[7:].strip().encode(), expected.encode()):
            return "muse"
        raise HTTPException(401, "Wrong upload token.")
    user = user_for_token(session, request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(401, "Send the upload token as 'Authorization: Bearer <token>', or log in.")
    return user.username


def _stamp() -> str:
    # The random suffix keeps two uploads in the same second from overwriting each other.
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ") + "-" + secrets.token_hex(3)


@router.post("/import")
async def upload(request: Request, source: str = Depends(allow_upload), session: Session = Depends(get_session)):
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Upload is over {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    body = await request.body()
    if len(body) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Upload is over {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    if not body.strip():
        raise HTTPException(400, "The upload is empty.")
    if not _one_at_a_time.acquire(blocking=False):
        raise HTTPException(409, "Another import is running; try again in a minute.")
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / f"reels-upload-{_stamp()}.json"
        path.write_bytes(body)
        label = f"{path.name} (from {source})"
        try:
            summary = run([path], session)
        except ExportParseError as e:
            bad = path.with_suffix(".invalid")
            path.replace(bad)
            message = str(e).replace(str(path), bad.name)
            record_run(session, "upload", f"{bad.name} (from {source})", error=message)
            raise HTTPException(400, f"Not imported: {message}") from e
        except UnicodeDecodeError as e:
            bad = path.with_suffix(".invalid")
            path.replace(bad)
            record_run(session, "upload", f"{bad.name} (from {source})", error="not UTF-8 text")
            raise HTTPException(400, "Not imported: the upload isn't UTF-8 text.") from e
        record_run(session, "upload", label, summary)
        backup.save_log_quietly(session)
        return {"saved_as": path.name, **summary.as_dict()}
    finally:
        _one_at_a_time.release()


@router.get("/imports", dependencies=[Depends(require_user)])
def recent_imports(session: Session = Depends(get_session), limit: int = 10):
    rows = session.scalars(select(ImportRun).order_by(ImportRun.id.desc()).limit(min(limit, 50)))
    return [
        {
            "at": r.created_at.isoformat() + "Z", "source": r.source, "filename": r.filename, "ok": r.ok, "error": r.error,
            "imported": r.imported, "pinned": r.pinned, "approximate": r.approximate,
            "needs_review": r.needs_review, "skipped": r.skipped, "merged": r.merged,
        }
        for r in rows
    ]
