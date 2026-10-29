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
REAL_DELIVER = notify.deliver   # the autouse fixture below replaces notify.deliver; tests of the real senders use this


@pytest.fixture(autouse=True)
def fresh_db(monkeypatch):
    init_db()
    db = SessionLocal()
    for model in (Vote, VoteReceipt, AuthSession, AuditLog, Candidate, Position, Voter, Admin):
        db.query(model).delete()
    db.query(Setting).filter(Setting.key.like("delivery.%") | Setting.key.like("license.%")).delete(synchronize_session=False)
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


# ---------- license: a throw-away key pair and a valid license.bat for every test ----------
class LicenseKit:
    """Test helper: the signing key, the license file location, and ways to (re)write or damage the file."""

    def __init__(self, path, private):
        self.path, self.private = path, private

    def write(self, days=30, licensee="Test Polytechnic", today=None):
        import license_tool
        from datetime import date, timedelta
        today = today or date.today()
        import tempfile, os
        fd, key_path = tempfile.mkstemp(suffix=".pem")
        os.close(fd)
        os.remove(key_path)
        from cryptography.hazmat.primitives import serialization
        with open(key_path, "wb") as f:
            f.write(self.private.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        try:
            license_tool.issue(key_path, licensee, today + timedelta(days=days), self.path, today=today)
        finally:
            os.remove(key_path)
        return self.text()

    def text(self):
        return self.path.read_bytes().decode("utf-8")

    def replace(self, old, new):
        raw = self.path.read_bytes().decode("utf-8")
        assert old in raw, old
        self.path.write_bytes(raw.replace(old, new).encode("utf-8"))

    def unlock_code(self, lock_id):
        import base64
        from core import licensing
        return base64.urlsafe_b64encode(self.private.sign(licensing.unlock_message(lock_id))).decode().rstrip("=")


@pytest.fixture(autouse=True)
def lic(fresh_db, tmp_path, monkeypatch):
    import base64
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from core import config, licensing
    private = Ed25519PrivateKey.generate()
    public_b64 = base64.b64encode(private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    monkeypatch.setattr(licensing, "PUBLIC_KEY_B64", public_b64)
    monkeypatch.setattr(licensing, "CACHE_SECONDS", 0)
    monkeypatch.setattr(config, "LICENSE_FILE", str(tmp_path / "license.bat"))
    licensing.reset_cache()
    kit = LicenseKit(tmp_path / "license.bat", private)
    kit.write()
    yield kit
    licensing.reset_cache()
