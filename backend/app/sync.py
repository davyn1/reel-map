"""Live sync: a counter of changes to shared data, for open apps to poll (GET /api/version).

Every flush that adds, changes or deletes a place, reel, visit, import run or account bumps
app_state.version in the same transaction. The app asks for the number every few seconds while
it's on screen and re-fetches only when it moved, so the other phone's changes and Muse's
uploads show up without a reload.

The hook is on SQLAlchemy's Session class, so it covers every session: requests, the CLI
importer, the demo reset and tests. Login sessions and alert bookkeeping don't count: they
change nothing anyone sees. Bulk UPDATE/DELETE statements skip flush events; the only one
(users.py taking over pre-login visits) is a one-off CLI step.
"""

from sqlalchemy import event, text
from sqlalchemy.orm import Session

from app.models import AlertSent, AppState, LoginSession

_IGNORED = (LoginSession, AlertSent, AppState)

_BUMP = text(
    "INSERT INTO app_state (id, version) VALUES (1, 1) "
    "ON CONFLICT (id) DO UPDATE SET version = version + 1"
)


def _changes_shared_data(session: Session) -> bool:
    for obj in (*session.new, *session.deleted):
        if not isinstance(obj, _IGNORED):
            return True
    return any(not isinstance(obj, _IGNORED) and session.is_modified(obj) for obj in session.dirty)


@event.listens_for(Session, "before_flush")
def _bump_on_change(session: Session, flush_context, instances) -> None:
    # Decided before the flush (the new/dirty/deleted lists are still filled in), written in the same
    # transaction, so a rolled-back change doesn't bump the version.
    if _changes_shared_data(session):
        session.info["sync_bump"] = True


@event.listens_for(Session, "after_flush")
def _write_bump(session: Session, flush_context) -> None:
    if session.info.pop("sync_bump", False):
        session.connection().execute(_BUMP)


def current(session: Session) -> int:
    """The current version; 0 before anything has changed."""
    state = session.get(AppState, 1, populate_existing=True)
    return state.version if state else 0
