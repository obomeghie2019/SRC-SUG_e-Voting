"""The license seal: deleting, editing or expiring license.bat blocks the application, and repeated tampering escalates."""
import base64
import os
import stat
from datetime import timedelta

import pytest

import license_tool
from core import licensing
from core.db import SessionLocal
from core.models import AuditLog, Setting
from tests.conftest import LOC, REAL_DELIVER  # noqa: F401  (conftest patches deliver; import keeps fixtures consistent)

W = "/api/web"


@pytest.fixture(autouse=True)
def tolerant(monkeypatch):
    """This file tests the forgiving setting (3 incidents). The strict default is tested in test_license_strict.py."""
    monkeypatch.setattr(licensing, "MAX_STRIKES", 3)


def state():
    db = SessionLocal()
    try:
        import json
        row = db.get(Setting, licensing.STATE_KEY)
        return json.loads(row.value) if row else {}
    finally:
        db.close()


def events(name):
    db = SessionLocal()
    try:
        return db.query(AuditLog).filter(AuditLog.event == name).count()
    finally:
        db.close()


def kind(client, base=W):
    return client.get(f"{base}/license").json()["kind"]


# ---------------- normal operation ----------------
def test_valid_license_lets_everything_through(web, lic):
    assert web.get(f"{W}/config").status_code == 200
    info = web.get(f"{W}/license").json()
    assert info["valid"] is True and info["licensee"] == "Test Polytechnic" and info["days_left"] == 30
    assert set(info) == {"valid", "kind", "message", "licensee", "expires", "days_left", "locked", "lock_id"}


def test_line_endings_bom_and_trailing_spaces_are_tolerated(web, lic):
    raw = lic.text()
    lic.path.write_bytes(b"\xef\xbb\xbf" + raw.replace("\r\n", "\n").replace("pause", "pause   ").encode("utf-8") + b"\n\n\n")
    assert web.get(f"{W}/config").status_code == 200


# ---------------- deleting / altering the file ----------------
def test_deleted_license_blocks_everything(web, mobile, lic):
    assert web.get(f"{W}/config").status_code == 200           # the app has had a valid license
    lic.path.unlink()
    for client, base in ((web, W), (mobile, "/api/mobile")):
        r = client.get(f"{base}/config")
        assert r.status_code == 403 and r.json()["license"]["kind"] == "missing"
        assert r.json()["detail"].startswith("License")
        assert client.post(f"{base}/auth/lookup", json={"matric_no": "T/001", **LOC}).status_code == 403
        assert kind(client, base) == "missing"                  # the status endpoint stays reachable
    assert web.get("/docs").status_code == 403                  # nothing else is served either


@pytest.mark.parametrize("edit", [
    lambda lic: lic.replace("REM LICENSEE: Test Polytechnic", "REM LICENSEE: Someone Else"),
    lambda lic: lic.replace("REM EXPIRES:", "REM EXPIRES: 2099-12-31\r\nREM EXPIRES:"),      # extra line
    lambda lic: lic.replace("pause", "pause\r\nformat c:"),                                  # changed command part
    lambda lic: lic.replace("REM ISSUED: ", "REM ISSUED: 1999-01-01\r\nREM NOTE: "),                   # inserted text
])
def test_any_edit_breaks_the_seal(web, lic, edit):
    web.get(f"{W}/config")
    edit(lic)
    r = web.get(f"{W}/config")
    assert r.status_code == 403 and r.json()["license"]["kind"] == "tampered"


def test_expiry_date_edit_is_caught_even_when_the_edit_is_a_real_extension(web, lic):
    web.get(f"{W}/config")
    lic.replace("REM EXPIRES: ", "REM EXPIRES: 2099-01-01 #")
    assert web.get(f"{W}/config").status_code == 403


def test_signature_from_another_key_is_rejected(web, lic):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    web.get(f"{W}/config")
    attacker = Ed25519PrivateKey.generate()
    body = licensing.canonical(lic.text())
    forged = base64.b64encode(attacker.sign(body)).decode()
    real = [ln for ln in lic.text().splitlines() if ln.startswith("REM SIGNATURE:")][0]
    lic.replace(real, f"REM SIGNATURE: {forged}")
    assert kind(web) == "tampered"


def test_signature_line_removed_or_garbled(web, lic):
    web.get(f"{W}/config")
    real = [ln for ln in lic.text().splitlines() if ln.startswith("REM SIGNATURE:")][0]
    lic.replace(real, "REM SIGNATURE: not-base64!!")
    assert kind(web) == "tampered"
    lic.replace("REM SIGNATURE: not-base64!!", "")
    assert kind(web) == "tampered"


def test_empty_and_binary_files(web, lic):
    web.get(f"{W}/config")
    lic.path.write_bytes(b"")
    assert kind(web) == "tampered"
    lic.path.write_bytes(b"\xff\xfe\x00garbage")
    assert kind(web) == "tampered"


# ---------------- expiry, renewal, clock ----------------
def test_expired_license_blocks_and_a_renewal_unblocks(web, lic):
    lic.write(days=0)                                              # valid through today
    assert web.get(f"{W}/config").status_code == 200
    db = SessionLocal()
    tomorrow = licensing.utcnow() + timedelta(days=1, hours=1)
    status = licensing.evaluate(db, now=tomorrow)
    db.close()
    assert status.kind == "expired" and "expired on" in status.message and not status.valid
    lic.write(days=60)                                             # renewed
    assert web.get(f"{W}/config").status_code == 200
    assert state()["strikes"] == 0


def test_clock_set_back_is_detected(web, lic):
    web.get(f"{W}/config")                                         # records the latest time seen
    db = SessionLocal()
    now = licensing.utcnow()
    assert licensing.evaluate(db, now=now - timedelta(hours=5)).valid          # within tolerance
    s = licensing.evaluate(db, now=now - timedelta(days=5))
    db.close()
    assert s.kind == "clock" and not s.valid


# ---------------- escalation ----------------
def test_fresh_install_without_a_license_is_not_a_strike(web, lic):
    original = lic.text()
    db = SessionLocal()                                             # forget that a valid license was ever seen
    db.query(Setting).filter(Setting.key == licensing.STATE_KEY).delete()
    db.commit()
    db.close()
    licensing.reset_cache()
    lic.path.unlink()
    assert web.get(f"{W}/config").status_code == 403
    assert state().get("strikes", 0) == 0
    lic.path.write_bytes(original.encode("utf-8"))
    assert web.get(f"{W}/config").status_code == 200


def test_repeated_tampering_hard_locks_until_the_vendor_unlocks(web, lic):
    original = lic.text()
    web.get(f"{W}/config")                                          # armed: a valid license was seen
    for expected in (1, 2):
        lic.path.unlink()
        assert web.get(f"{W}/config").status_code == 403
        assert web.get(f"{W}/config").status_code == 403            # many requests in one incident = one strike
        assert state()["strikes"] == expected
        lic.path.write_bytes(original.encode("utf-8"))
        assert web.get(f"{W}/config").status_code == 200            # first strikes recover when the file is restored
    lic.replace("REM LICENSEE: Test Polytechnic", "REM LICENSEE: Edited")        # third incident
    r = web.get(f"{W}/config")
    assert r.status_code == 403 and r.json()["license"]["kind"] == "locked"
    lock_id = r.json()["license"]["lock_id"]
    assert len(lock_id) == 8 and lock_id in r.json()["detail"]
    assert events("license_tamper") == 3 and events("license_hard_lock") == 1

    lic.path.write_bytes(original.encode("utf-8"))                  # restoring the genuine file no longer helps
    assert web.get(f"{W}/config").json()["license"]["kind"] == "locked"
    assert licensing.evaluate(SessionLocal()).kind == "locked"

    bad = web.post(f"{W}/license/unlock", json={"token": "A" * 86})
    assert bad.status_code == 400
    wrong_lock = web.post(f"{W}/license/unlock", json={"token": lic.unlock_code("DEADBEEF")})
    assert wrong_lock.status_code == 400                            # a code made for another lock id is useless
    ok = web.post(f"{W}/license/unlock", json={"token": lic.unlock_code(lock_id)})
    assert ok.status_code == 200 and ok.json()["valid"] is True
    assert web.get(f"{W}/config").status_code == 200
    assert state()["strikes"] == 0 and events("license_unlocked") == 1
    assert web.post(f"{W}/license/unlock", json={"token": lic.unlock_code(lock_id)}).status_code == 409   # not locked now


def test_unlock_attempts_are_rate_limited(web, lic):
    web.get(f"{W}/config")
    codes = [web.post(f"{W}/license/unlock", json={"token": "A" * 86}).status_code for _ in range(3)]
    assert codes == [409, 409, 409]                                 # not locked: refused without counting as guesses
    original = lic.text()
    for _ in range(3):
        lic.path.unlink()
        web.get(f"{W}/config")
        lic.path.write_bytes(original.encode("utf-8"))
        web.get(f"{W}/config")
    results = [web.post(f"{W}/license/unlock", json={"token": "B" * 86}).status_code for _ in range(12)]
    assert results[:10] == [400] * 10 and results[10:] == [429, 429]


def test_a_new_genuine_license_clears_strikes_but_not_a_hard_lock(web, lic):
    web.get(f"{W}/config")
    lic.path.unlink()
    web.get(f"{W}/config")
    assert state()["strikes"] == 1
    lic.write(days=90)                                              # vendor sends a renewal (new license id)
    assert web.get(f"{W}/config").status_code == 200
    assert state()["strikes"] == 0


# ---------------- not configured, middleware details, fail closed ----------------
def test_without_a_public_key_nothing_runs(web, lic, monkeypatch):
    monkeypatch.setattr(licensing, "PUBLIC_KEY_B64", "")
    r = web.get(f"{W}/config")
    assert r.status_code == 403 and r.json()["license"]["kind"] == "not_configured"


def test_options_preflight_and_cors_headers_on_blocked_responses(web, lic):
    web.get(f"{W}/config")
    lic.path.unlink()
    r = web.get(f"{W}/config", headers={"Origin": "http://localhost:5173"})
    assert r.status_code == 403 and r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    pre = web.options(f"{W}/config", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert pre.status_code == 200


def test_check_that_cannot_run_fails_closed(web, lic, monkeypatch):
    def boom(db):
        raise RuntimeError("database down")
    monkeypatch.setattr(licensing, "check", boom)
    r = web.get(f"{W}/config")
    assert r.status_code == 503 and r.json()["detail"].startswith("License")


def test_license_state_is_not_exposed_through_admin_settings(web, lic):
    web.get(f"{W}/config")
    t = web.post(f"{W}/auth/admin/login", json={"username": "admin", "password": "secret-admin"}).json()["token"]
    body = web.get(f"{W}/admin/settings", headers={"Authorization": f"Bearer {t}"}).text
    assert "license." not in body and "strikes" not in body


# ---------------- the vendor tool ----------------
def test_tool_keygen_issue_status_unlock(tmp_path, capsys, monkeypatch):
    key = tmp_path / "private.pem"
    pub_py = tmp_path / "license_public.py"
    pub = license_tool.keygen(str(key), pub_py)
    assert pub in pub_py.read_text() and key.exists()
    if os.name != "nt":
        assert stat.S_IMODE(key.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError):
        license_tool.keygen(str(key), pub_py)                       # never overwrites a private key

    monkeypatch.setattr(licensing, "PUBLIC_KEY_B64", pub)
    out = tmp_path / "license.bat"
    from datetime import date
    license_tool.issue(str(key), "Auchi\nPolytechnic", date.today() + timedelta(days=31), out)
    raw = out.read_bytes()
    assert b"\r\n" in raw and raw.count(b"\n") == raw.count(b"\r\n")            # CRLF only
    text = raw.decode()
    assert "REM LICENSEE: Auchi Polytechnic" in text and text.startswith("@echo off") and "SIGNATURE:" in text
    assert license_tool.status(out) == 0
    assert "VALID" in capsys.readouterr().out

    out.write_bytes(raw.replace(b"Auchi", b"Evil"))
    assert license_tool.status(out) == 1
    assert "License" in capsys.readouterr().out
    assert license_tool.status(tmp_path / "nothing.bat") == 1

    code = license_tool.unlock_code(str(key), "ab12cd34")
    assert code and "=" not in code
    with pytest.raises(SystemExit):
        license_tool.issue(str(key), "   ", date.today() + timedelta(days=1), out)
    with pytest.raises(SystemExit):
        license_tool.issue(str(key), "X", date.today() - timedelta(days=1), out)


def test_tool_expired_status_and_cli_entry_points(tmp_path, capsys, monkeypatch):
    key = tmp_path / "k.pem"
    monkeypatch.setattr(licensing, "PUBLIC_KEY_B64", license_tool.keygen(str(key), tmp_path / "p.py"))
    out = tmp_path / "license.bat"
    from datetime import date
    today = date.today() - timedelta(days=10)
    license_tool.issue(str(key), "Old Co", date.today() - timedelta(days=3), out, today=today)
    assert license_tool.status(out) == 1 and "EXPIRED" in capsys.readouterr().out
    assert license_tool.main(["unlock", "--key", str(key), "--lock-id", "ab12cd34"]) == 0
    assert license_tool.main(["issue", "--key", str(key), "--licensee", "Poly", "--days", "5", "--out", str(out)]) == 0
    monkeypatch.setattr(licensing.config, "LICENSE_FILE", str(out))
    assert license_tool.main(["status"]) == 0
    assert license_tool.main(["issue", "--key", str(key), "--licensee", "Poly", "--expires", "2099-01-01", "--out", str(out)]) == 0


def test_tool_apply_unlock_when_not_locked(capsys):
    assert license_tool.apply_unlock("A" * 40) == 1
    assert "not locked" in capsys.readouterr().out
