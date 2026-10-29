"""Default (strict) behaviour: deleting or editing license.bat locks the application until the vendor unlocks it
with a signed code or issues a brand-new license file."""
from datetime import date, timedelta

import pytest

from core import licensing
from core.db import SessionLocal
from core.models import AuditLog

W = "/api/web"
M = "/api/mobile"


def lock_info(client, base=W):
    r = client.get(f"{base}/config")
    return r.status_code, r.json().get("license", {})


def armed(client):
    assert client.get(f"{W}/config").status_code == 200        # the app has run with a valid license


def test_strict_is_the_default():
    assert licensing.MAX_STRIKES == 1


def test_deleting_the_file_locks_web_and_mobile_and_the_original_does_not_help(web, mobile, lic):
    original = lic.text()
    armed(web)
    lic.path.unlink()
    for client, base in ((web, W), (mobile, M)):
        code, info = lock_info(client, base)
        assert code == 403 and info["kind"] == "locked" and len(info["lock_id"]) == 8
        assert "deleted or changed" in info["message"] and info["lock_id"] in info["message"]
    lic.path.write_bytes(original.encode("utf-8"))              # putting the original back
    for client, base in ((web, W), (mobile, M)):
        assert lock_info(client, base)[0] == 403


def test_editing_the_file_locks_immediately(web, lic):
    original = lic.text()
    armed(web)
    lic.replace("REM LICENSEE: Test Polytechnic", "REM LICENSEE: Edited")
    assert lock_info(web)[1]["kind"] == "locked"
    lic.path.write_bytes(original.encode("utf-8"))
    assert lock_info(web)[1]["kind"] == "locked"
    db = SessionLocal()
    assert db.query(AuditLog).filter(AuditLog.event == "license_hard_lock").count() == 1
    db.close()


def test_the_vendor_unlock_code_opens_it_again(web, lic):
    original = lic.text()
    armed(web)
    lic.path.unlink()
    lock_id = lock_info(web)[1]["lock_id"]
    lic.path.write_bytes(original.encode("utf-8"))
    assert web.post(f"{W}/license/unlock", json={"token": lic.unlock_code(lock_id)}).status_code == 200
    assert web.get(f"{W}/config").status_code == 200


def test_a_new_license_from_the_vendor_opens_it_again(web, mobile, lic):
    armed(web)
    lic.path.unlink()
    assert lock_info(web)[1]["kind"] == "locked"
    lic.write(days=45)                                          # the vendor issues a new license.bat
    assert web.get(f"{W}/config").status_code == 200
    assert mobile.get(f"{M}/config").status_code == 200


def test_an_older_license_cannot_be_used_to_open_the_lock(web, lic):
    armed(web)
    lic.path.unlink()
    assert lock_info(web)[1]["kind"] == "locked"
    lic.write(days=60, today=date.today() - timedelta(days=10))   # genuine, unexpired, but issued BEFORE the lock
    assert lock_info(web)[1]["kind"] == "locked"


def test_replaying_a_previous_or_current_license_cannot_open_the_lock(web, lic):
    first = lic.text()
    armed(web)
    second = lic.write(days=90)                                 # a renewal: both licenses are now known here
    armed(web)
    lic.path.unlink()
    assert lock_info(web)[1]["kind"] == "locked"
    for old in (first, second):
        lic.path.write_bytes(old.encode("utf-8"))
        assert lock_info(web)[1]["kind"] == "locked"


def test_expiry_is_not_a_tamper_and_a_renewal_opens_it(web, lic):
    lic.write(days=0)
    armed(web)
    db = SessionLocal()
    info = licensing.evaluate(db, now=licensing.utcnow() + timedelta(days=2))
    db.close()
    assert info.kind == "expired"                               # blocked, but no hard lock
    lic.write(days=60)
    assert web.get(f"{W}/config").status_code == 200


def test_a_fresh_install_without_a_license_is_blocked_but_not_locked(web, lic):
    from core.models import Setting
    original = lic.text()
    db = SessionLocal()
    db.query(Setting).filter(Setting.key == licensing.STATE_KEY).delete()   # never had a valid license
    db.commit()
    db.close()
    licensing.reset_cache()
    lic.path.unlink()
    assert lock_info(web)[1]["kind"] == "missing"
    lic.path.write_bytes(original.encode("utf-8"))
    assert web.get(f"{W}/config").status_code == 200
