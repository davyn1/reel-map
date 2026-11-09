"""Discord alerts when Muse's uploads go wrong, so a problem doesn't sit unnoticed on the map.

    FOOD_MAP_ALERT_WEBHOOK   a Discord webhook URL (a secret: anyone with it can post to the channel).
                             Unset = alerts off (local runs, tests, the demo).
    FOOD_MAP_QUIET_DAYS      days without a Muse upload before a "gone quiet" alert (default 7; Muse
                             only uploads on days something new was saved, so quiet days are normal)

What sends one:
- a Muse upload that's refused or fails to import (bad JSON, not UTF-8, empty, too big, import error)
- an upload with a wrong token (Muse's token no longer matching the server's, or a stranger)
- no Muse upload for FOOD_MAP_QUIET_DAYS, checked when the server starts and twice a day while it
  runs. The server sleeps when idle, so a daily GitHub Actions job (.github/workflows/wake.yml)
  wakes it.

Each kind has a cooldown (COOLDOWNS) so a repeating problem posts once, not on every attempt.
Sending never fails the request that triggered it.

    python -m app.alerts test     # post a test message to the webhook
    python -m app.alerts check    # run the quiet check now
"""

import json
import logging
import os
import sys
import threading
import urllib.request
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AlertSent, ImportRun

log = logging.getLogger(__name__)


def webhook() -> str:
    return os.getenv("FOOD_MAP_ALERT_WEBHOOK", "").strip()


def quiet_days() -> int:
    return int(os.getenv("FOOD_MAP_QUIET_DAYS", "7"))


COOLDOWNS = {
    "upload_failed": timedelta(hours=1),
    "wrong_token": timedelta(hours=6),
}  # "quiet" has its own rule: once per quiet stretch, then again if it stays quiet that long


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _post(text: str) -> None:
    body = json.dumps({"content": text[:1900], "allowed_mentions": {"parse": []}}).encode()
    # Discord refuses Python's default user agent.
    req = urllib.request.Request(webhook(), data=body, method="POST",
                                 headers={"Content-Type": "application/json", "User-Agent": "yums-map-alerts/1.0"})
    try:
        urllib.request.urlopen(req, timeout=10).close()
    except Exception as e:  # noqa: BLE001
        log.warning("Discord alert failed: %s", e)


def _send(session: Session, kind: str, text: str, wait: bool) -> bool:
    """Record that `kind` went out now, then post it."""
    if not webhook():
        return False
    row = session.get(AlertSent, kind)
    if row is None:
        session.add(AlertSent(kind=kind, sent_at=_now()))
    else:
        row.sent_at = _now()
    session.commit()
    if wait:
        _post(text)
    else:  # don't hold up the upload's response on Discord
        threading.Thread(target=_post, args=(text,), daemon=True).start()
    return True


def alert(session: Session, kind: str, text: str, wait: bool = False) -> bool:
    """Post `text` unless this kind went out within its cooldown. Returns whether it was sent."""
    row = session.get(AlertSent, kind)
    if row is not None and _now() - row.sent_at < COOLDOWNS[kind]:
        return False
    return _send(session, kind, text, wait)


def upload_failed(session: Session, reason: str) -> None:
    alert(session, "upload_failed", f"⚠️ **Muse upload not imported.** {reason}")


def wrong_token(session: Session) -> None:
    alert(session, "wrong_token", "⚠️ **An upload was refused: wrong token.** If that was Muse, its token no longer "
                                  "matches the server's (FOOD_MAP_IMPORT_TOKEN).")


def check_quiet(session: Session, wait: bool = False) -> bool:
    """Alert if Muse hasn't uploaded successfully in quiet_days(). Before its first upload, stay silent."""
    last = session.scalars(
        select(ImportRun.created_at)
        .where(ImportRun.source == "upload", ImportRun.ok.is_(True), ImportRun.filename.like("%(from muse)"))
        .order_by(ImportRun.created_at.desc())
    ).first()
    if last is None or _now() - last < timedelta(days=quiet_days()):
        return False
    sent = session.get(AlertSent, "quiet")
    if sent is not None and sent.sent_at > last and _now() - sent.sent_at < timedelta(days=quiet_days()):
        return False  # already said so for this stretch
    days = (_now() - last).days
    return _send(session, "quiet", f"🤫 **No upload from Muse in {days} days** (last one {last:%b %d}). That's fine if "
                                    f"you haven't saved any food reels since; otherwise check Muse's upload setup.", wait)


def main(argv=None) -> int:
    from app.db import SessionLocal, init_db

    argv = sys.argv[1:] if argv is None else argv
    if argv not in (["test"], ["check"]):
        print(__doc__)
        return 1
    if not webhook():
        print("FOOD_MAP_ALERT_WEBHOOK isn't set, so alerts are off.")
        return 1
    if argv == ["test"]:
        _post("✅ Yums Map alerts are working.")
        print("Sent a test message.")
        return 0
    init_db()
    with SessionLocal() as session:
        print("Sent a quiet alert." if check_quiet(session, wait=True) else "Nothing to report.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
