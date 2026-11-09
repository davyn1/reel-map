import types
from datetime import datetime, timedelta, timezone

import pytest

from app import alerts
from app.models import AlertSent, ImportRun
from app.routers import imports
from tests.test_api import client, db, login  # noqa: F401  (fixtures)
from tests.test_imports import NEW, TOKEN, post, token  # noqa: F401  (token is a fixture)


@pytest.fixture
def sent(monkeypatch):
    """Alerts on, posting into a list instead of Discord, synchronously."""
    monkeypatch.setenv("FOOD_MAP_ALERT_WEBHOOK", "https://discord.example/webhook")
    messages: list[str] = []
    monkeypatch.setattr(alerts, "_post", messages.append)

    class NowThread:
        def __init__(self, target, args, daemon):
            self.go = lambda: target(*args)

        def start(self):
            self.go()

    monkeypatch.setattr(alerts, "threading", types.SimpleNamespace(Thread=NowThread))
    return messages


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_no_webhook_no_alerts(db, token, monkeypatch):
    monkeypatch.delenv("FOOD_MAP_ALERT_WEBHOOK", raising=False)
    posted = []
    monkeypatch.setattr(alerts, "_post", posted.append)
    assert post("[{bad", token=TOKEN).status_code == 400
    assert posted == []


def test_bad_muse_upload_alerts_once_an_hour(db, token, sent):
    assert post("[{bad").status_code == 400
    assert post("[{still bad").status_code == 400
    assert len(sent) == 1 and "Muse upload not imported" in sent[0] and "line 1" in sent[0]


def test_empty_or_wrong_token_uploads_alert(db, token, sent):
    assert post("   ").status_code == 400
    assert post(NEW, token="wrong").status_code == 401
    assert post(NEW, token="wrong again").status_code == 401
    assert [m.split("**")[1] for m in sent] == ["Muse upload not imported.", "An upload was refused: wrong token."]


def test_a_person_uploading_sees_the_error_instead(client, token, sent):
    res = client.post("/api/import", content="[{bad", headers={"Content-Type": "application/json"})
    assert res.status_code == 400 and sent == []


def test_an_import_crash_is_recorded_and_alerted(db, token, sent, monkeypatch):
    def boom(paths, session):
        raise RuntimeError("disk full")

    monkeypatch.setattr(imports, "run", boom)
    res = post(NEW)
    assert res.status_code == 500 and "Import failed on the server" in res.json()["detail"]
    with db() as s:
        last = s.query(ImportRun).order_by(ImportRun.id.desc()).first()
        assert not last.ok and "disk full" in last.error
    assert len(sent) == 1


def muse_upload_days_ago(s, days):
    s.add(ImportRun(created_at=now() - timedelta(days=days), source="upload", filename="x.json (from muse)", ok=True))
    s.commit()


def test_quiet_check(db, sent):
    with db() as s:
        assert not alerts.check_quiet(s)  # Muse has never uploaded: nothing to compare against
        muse_upload_days_ago(s, 3)
        assert not alerts.check_quiet(s)
        s.query(ImportRun).delete()
        muse_upload_days_ago(s, 8)
        assert alerts.check_quiet(s) and "No upload from Muse in 8 days" in sent[-1]
        assert not alerts.check_quiet(s)  # said once for this quiet stretch

        # Muse uploads again, then goes quiet again later: a new alert
        s.query(ImportRun).delete()
        muse_upload_days_ago(s, 9)
        s.get(AlertSent, "quiet").sent_at = now() - timedelta(days=10)
        s.commit()
        assert alerts.check_quiet(s)
    assert len(sent) == 2


def test_quiet_check_ignores_failed_and_hand_uploads(db, sent):
    with db() as s:
        muse_upload_days_ago(s, 10)
        s.add(ImportRun(created_at=now(), source="upload", filename="y.invalid (from muse)", ok=False))
        s.add(ImportRun(created_at=now(), source="upload", filename="z.json (from bigbacking)", ok=True))
        s.commit()
        assert alerts.check_quiet(s)
