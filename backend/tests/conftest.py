"""Test setup: a throw-away SQLite database and OTP codes captured in memory (nothing is really sent)."""
import os
import sys
import tempfile

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp()
os.environ["JWT_SECRET"] = "test-secret-" + "x" * 40
os.environ["OTP_DEV_MODE"] = "true"
os.environ["LOCATION_REQUIRED"] = "true"
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from core import notify, services  # noqa: E402
from core.db import SessionLocal, init_db  # noqa: E402
from core.models import Admin, AuditLog, AuthSession, Candidate, Position, Setting, Vote, VoteReceipt, Voter  # noqa: E402
from core.security import hash_pw  # noqa: E402

CODES: list[str] = []


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    init_db()
    db = SessionLocal()
    for model in (Vote, VoteReceipt, AuthSession, AuditLog, Candidate, Position, Voter, Admin):
        db.query(model).delete()
    db.query(Setting).filter(Setting.key.like("delivery.%")).delete(synchronize_session=False)
    db.commit()
    db.add(Admin(username="admin", full_name="Admin", password_hash=hash_pw("secret-admin")))
    p = Position(title="President")
    p.candidates = [Candidate(full_name="Ada"), Candidate(full_name="Bayo")]
    db.add(p)
    db.commit()
    services.import_voters(db, [
        {"matric_no": "T/001", "full_name": "Test One", "email": "one@example.com", "phone": "08011111111"},
        {"matric_no": "T/002", "full_name": "Test Two", "email": "two@example.com", "phone": ""},
        {"matric_no": "T/003", "full_name": "No Contact"},
    ])
    services.set_status(db, "open")
    db.close()
    CODES.clear()
    monkeypatch.setattr(notify, "deliver", lambda cfg, channel, voter, code, institution: CODES.append(code))


@pytest.fixture
def web():
    from api_web.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mobile():
    from api_mobile.main import app
    with TestClient(app) as c:
        yield c


LOC = {"latitude": 6.5244, "longitude": 3.3792, "accuracy_m": 12.0}


def sign_in(client, base, matric="T/001", channel="email", code=None):
    r = client.post(f"{base}/auth/lookup", json={"matric_no": matric, "device_id": "dev-abc-12345", **LOC})
    assert r.status_code == 200, r.text
    sid = r.json()["session_id"]
    assert client.post(f"{base}/auth/otp/send", json={"session_id": sid, "channel": channel}).status_code == 200
    r = client.post(f"{base}/auth/otp/verify", json={"session_id": sid, "otp": code or CODES[-1], **LOC})
    return sid, r
