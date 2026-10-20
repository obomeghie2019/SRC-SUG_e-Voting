from datetime import timedelta

from core import audit
from core.db import SessionLocal
from core.models import AuthSession, Position, Voter
from tests.conftest import CODES, LOC, sign_in

W = "/api/web"


def ballot_selection(client, token):
    b = client.get(f"{W}/ballot", headers={"Authorization": f"Bearer {token}"}).json()
    p = b["positions"][0]
    return {str(p["id"]): p["candidates"][0]["id"]}


def test_full_flow_and_single_vote(web):
    _, r = sign_in(web, W)
    assert r.status_code == 200
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    body = {"selections": ballot_selection(web, token), **LOC}
    assert web.post(f"{W}/vote", json=body, headers=h).status_code == 200
    # second attempt with the same token is refused (session is used) ...
    assert web.post(f"{W}/vote", json=body, headers=h).status_code == 401
    # ... and signing in again is refused because the voter has voted
    r = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC})
    assert r.status_code == 409


def test_location_is_required(web):
    r = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001"})
    assert r.status_code == 400 and "location" in r.json()["detail"].lower()


def test_voting_must_be_open(web):
    db = SessionLocal()
    from core import services
    services.set_status(db, "closed")
    db.close()
    r = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC})
    assert r.status_code == 403


def test_unknown_matric(web):
    assert web.post(f"{W}/auth/lookup", json={"matric_no": "NOPE/1", **LOC}).status_code == 404


def test_only_channels_on_record_are_offered(web):
    r = web.post(f"{W}/auth/lookup", json={"matric_no": "T/002", **LOC}).json()
    assert [c["channel"] for c in r["channels"]] == ["email"]          # no phone on record
    sid = r["session_id"]
    assert web.post(f"{W}/auth/otp/send", json={"session_id": sid, "channel": "sms"}).status_code == 400
    assert web.post(f"{W}/auth/lookup", json={"matric_no": "T/003", **LOC}).status_code == 422  # no contact at all


def test_contacts_are_masked(web):
    r = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC}).json()
    masked = {c["channel"]: c["masked"] for c in r["channels"]}
    assert masked["email"].startswith("o***@") and "one@" not in masked["email"]
    assert masked["sms"].startswith("+234") and "8011111" not in masked["sms"]


def test_wrong_code_locks_session(web):
    r = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC}).json()
    sid = r["session_id"]
    web.post(f"{W}/auth/otp/send", json={"session_id": sid, "channel": "sms"})
    wrong = "000000" if CODES[-1] != "000000" else "111111"
    for _ in range(5):
        assert web.post(f"{W}/auth/otp/verify", json={"session_id": sid, "otp": wrong}).status_code == 401
    # even the right code no longer works
    assert web.post(f"{W}/auth/otp/verify", json={"session_id": sid, "otp": CODES[-1]}).status_code == 409


def test_code_is_bound_to_its_session(web):
    a = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC}).json()["session_id"]
    web.post(f"{W}/auth/otp/send", json={"session_id": a, "channel": "email"})
    code_a = CODES[-1]
    b = web.post(f"{W}/auth/lookup", json={"matric_no": "T/002", **LOC}).json()["session_id"]
    web.post(f"{W}/auth/otp/send", json={"session_id": b, "channel": "email"})
    # voter T/002's session cannot be opened with voter T/001's code
    wrong = web.post(f"{W}/auth/otp/verify", json={"session_id": b, "otp": code_a})
    assert wrong.status_code in (401, 200) and (wrong.status_code == 401 or code_a == CODES[-1])


def test_expired_code(web):
    r = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC}).json()
    sid = r["session_id"]
    web.post(f"{W}/auth/otp/send", json={"session_id": sid, "channel": "email"})
    db = SessionLocal()
    s = db.get(AuthSession, sid)
    s.otp_expires_at = audit.utcnow() - timedelta(minutes=1)
    db.commit()
    db.close()
    assert web.post(f"{W}/auth/otp/verify", json={"session_id": sid, "otp": CODES[-1]}).status_code == 410


def test_send_rate_limit(web):
    sid = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC}).json()["session_id"]
    codes = [web.post(f"{W}/auth/otp/send", json={"session_id": sid, "channel": "email"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]


def test_web_token_rejected_by_mobile_api(web, mobile):
    _, r = sign_in(web, W)
    token = r.json()["token"]
    assert mobile.get("/api/mobile/ballot", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_mobile_flow_and_forensic_report(web, mobile):
    _, r = sign_in(mobile, "/api/mobile", matric="T/002")
    assert r.status_code == 200
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    b = mobile.get("/api/mobile/ballot", headers=h).json()
    p = b["positions"][0]
    r = mobile.post("/api/mobile/vote", json={"selections": {str(p["id"]): p["candidates"][1]["id"]}, **LOC}, headers=h)
    assert r.status_code == 200

    admin = web.post(f"{W}/auth/admin/login", json={"username": "admin", "password": "secret-admin"}).json()["token"]
    rep = web.get(f"{W}/admin/reports/forensic", headers={"Authorization": f"Bearer {admin}"}).json()
    assert rep["summary"]["total_votes"] == 1
    row = rep["rows"][0]
    assert row["matric_no"] == "T/002" and row["app"] == "mobile" and row["otp_channel"] == "email"
    assert row["latitude"] == LOC["latitude"] and row["longitude"] == LOC["longitude"]
    assert row["ip"] and row["device_id"] == "dev-abc-12345"
    # ballot secrecy: nothing about the choice is in the report
    assert "candidate" not in " ".join(row.keys()).lower()


def test_admin_endpoints_need_admin_token(web):
    assert web.get(f"{W}/admin/reports/forensic").status_code == 401
    _, r = sign_in(web, W)
    voter_h = {"Authorization": f"Bearer {r.json()['token']}"}
    assert web.get(f"{W}/admin/reports/forensic", headers=voter_h).status_code == 403


def test_voter_and_candidate_csv_import(web):
    admin = web.post(f"{W}/auth/admin/login", json={"username": "admin", "password": "secret-admin"}).json()["token"]
    h = {"Authorization": f"Bearer {admin}"}
    csv_v = b"matric_no,full_name,email,phone,department,level\nN/100,New Voter,new@example.com,0802 222 3333,CS,ND1\nT/003,No Contact,nc@example.com,08033334444,,\n"
    r = web.post(f"{W}/admin/voters/import", files={"file": ("v.csv", csv_v)}, headers=h).json()
    assert len(r["created"]) == 1 and len(r["updated"]) == 1
    db = SessionLocal()
    from sqlalchemy import select
    assert db.scalar(select(Voter.phone).where(Voter.matric_no == "N/100")) == "+2348022223333"
    db.close()

    from core import services
    db = SessionLocal()
    services.set_status(db, "draft")
    db.close()
    csv_c = b"position,full_name,department,level\nVice President,Chi,CS,ND2\nPresident,Ada,CS,ND2\nPresident,Dayo,CS,ND2\n"
    r = web.post(f"{W}/admin/candidates/import", files={"file": ("c.csv", csv_c)}, headers=h).json()
    assert len(r["created"]) == 2 and len(r["skipped"]) == 1   # Ada already exists
    db = SessionLocal()
    assert db.query(Position).count() == 2
    db.close()


# ---------- uploads and delivery-not-configured message ----------
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def admin_headers(web):
    t = web.post(f"{W}/auth/admin/login", json={"username": "admin", "password": "secret-admin"}).json()["token"]
    return {"Authorization": f"Bearer {t}"}


def test_logo_upload_serve_replace_remove(web):
    h = admin_headers(web)
    r = web.post(f"{W}/admin/settings/logo", files={"file": ("logo.png", PNG, "image/png")}, headers=h)
    assert r.status_code == 200
    url = r.json()["logo_url"]
    assert url.startswith("/uploads/") and url.endswith(".png")
    assert web.get(f"{W}/config").json()["logo_url"] == url                 # public config carries it
    assert web.get(f"/api/web{url}").status_code == 200                      # and the file is served
    url2 = web.post(f"{W}/admin/settings/logo", files={"file": ("b.png", PNG)}, headers=h).json()["logo_url"]
    assert web.get(f"/api/web{url}").status_code == 404                      # old file cleaned up
    assert web.delete(f"{W}/admin/settings/logo", headers=h).json() == {"logo_url": ""}
    assert web.get(f"/api/web{url2}").status_code == 404


def test_upload_rejects_non_images_and_large_files(web):
    h = admin_headers(web)
    assert web.post(f"{W}/admin/settings/logo", files={"file": ("x.png", b"<svg onload=alert(1)>")}, headers=h).status_code == 415
    assert web.post(f"{W}/admin/settings/logo", files={"file": ("x.png", b"just text")}, headers=h).status_code == 415
    big = PNG + b"\x00" * (2 * 1024 * 1024)
    assert web.post(f"{W}/admin/settings/logo", files={"file": ("big.png", big)}, headers=h).status_code == 413
    assert web.post(f"{W}/admin/settings/logo", files={"file": ("l.png", PNG)}).status_code == 401   # admin only


def test_candidate_photo_upload_draft_only(web):
    from core import services
    h = admin_headers(web)
    db = SessionLocal()
    services.set_status(db, "draft")
    cid = db.query(Position).first().candidates[0].id
    db.close()
    r = web.post(f"{W}/admin/candidates/{cid}/photo", files={"file": ("p.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 32)}, headers=h)
    assert r.status_code == 200 and r.json()["photo_url"].endswith(".jpg")
    assert web.get(f"/api/web{r.json()['photo_url']}").status_code == 200
    db = SessionLocal()
    services.set_status(db, "open")
    db.close()
    assert web.post(f"{W}/admin/candidates/{cid}/photo", files={"file": ("p.png", PNG)}, headers=h).status_code in (400, 403, 409)


def test_delivery_not_configured_gives_accurate_message(web, monkeypatch):
    from core import config
    monkeypatch.setattr(config, "OTP_DEV_MODE", False)
    r = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC})
    assert r.status_code == 503
    assert "not set up" in r.json()["detail"] and "on record" not in r.json()["detail"]


# ---------- admin Delivery settings (SMTP / SMS / code rules) ----------
def test_delivery_settings_roundtrip_and_secrets_hidden(web):
    from core.models import Setting
    h = admin_headers(web)
    r = web.put(f"{W}/admin/delivery", headers=h, json={
        "smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_user": "mailer", "smtp_password": "S3cret-Pass!",
        "smtp_from": "votes@school.edu.ng", "sms_provider": "termii", "sms_api_key": "KEY-12345", "sms_sender_id": "AUCHIPOLY",
        "otp_ttl_minutes": 7, "otp_dev_mode": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["smtp_host"] == "smtp.example.com" and body["otp_ttl_minutes"] == 7 and body["sources"]["smtp_host"] == "dashboard"
    assert body["secrets_set"] == {"smtp_password": True, "sms_api_key": True}
    assert "S3cret-Pass!" not in r.text and "KEY-12345" not in r.text          # never sent back
    assert "S3cret-Pass!" not in web.get(f"{W}/admin/delivery", headers=h).text
    assert "S3cret-Pass!" not in web.get(f"{W}/admin/settings", headers=h).text  # nor via general settings
    db = SessionLocal()
    stored = db.get(Setting, "delivery.smtp_password").value
    db.close()
    assert stored and "S3cret" not in stored                                  # encrypted at rest
    # a blank secret keeps the saved one; clear_secrets removes it
    web.put(f"{W}/admin/delivery", headers=h, json={"smtp_password": "", "smtp_host": "smtp2.example.com"})
    assert web.get(f"{W}/admin/delivery", headers=h).json()["secrets_set"]["smtp_password"] is True
    web.put(f"{W}/admin/delivery", headers=h, json={"clear_secrets": ["smtp_password"]})
    assert web.get(f"{W}/admin/delivery", headers=h).json()["secrets_set"]["smtp_password"] is False


def test_delivery_validation_and_admin_only(web):
    h = admin_headers(web)
    assert web.put(f"{W}/admin/delivery", headers=h, json={"smtp_port": 99999}).status_code == 400
    assert web.put(f"{W}/admin/delivery", headers=h, json={"sms_provider": "carrier-pigeon"}).status_code == 400
    assert web.put(f"{W}/admin/delivery", headers=h, json={"default_country_code": "abc"}).status_code == 400
    assert web.put(f"{W}/admin/delivery", headers=h, json={"otp_ttl_minutes": 0}).status_code == 400
    assert web.get(f"{W}/admin/delivery").status_code == 401
    _, r = sign_in(web, W)
    assert web.get(f"{W}/admin/delivery", headers={"Authorization": f"Bearer {r.json()['token']}"}).status_code == 403


def test_dashboard_settings_decide_which_channels_voters_see(web):
    h = admin_headers(web)
    # Test mode OFF and nothing configured -> accurate 'not set up' message
    web.put(f"{W}/admin/delivery", headers=h, json={"otp_dev_mode": False})
    assert web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC}).status_code == 503
    # configure email only -> only email is offered
    web.put(f"{W}/admin/delivery", headers=h, json={"smtp_host": "smtp.example.com", "smtp_from": "v@school.edu.ng"})
    r = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC}).json()
    assert [c["channel"] for c in r["channels"]] == ["email"]
    # add an SMS provider -> both
    web.put(f"{W}/admin/delivery", headers=h, json={"sms_provider": "termii", "sms_api_key": "k", "sms_sender_id": "S"})
    r = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC}).json()
    assert {c["channel"] for c in r["channels"]} == {"email", "sms"}
    assert r["otp_ttl_minutes"] == 5
    web.put(f"{W}/admin/delivery", headers=h, json={"otp_ttl_minutes": 9})
    assert web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC}).json()["otp_ttl_minutes"] == 9


def test_test_buttons(web):
    h = admin_headers(web)
    web.put(f"{W}/admin/delivery", headers=h, json={"otp_dev_mode": True})
    r = web.post(f"{W}/admin/delivery/test-email", headers=h, json={"to": "me@example.com"})
    assert r.status_code == 200 and "Test mode is ON" in r.json()["message"]
    assert web.post(f"{W}/admin/delivery/test-email", headers=h, json={"to": "not-an-email"}).status_code == 400
    assert web.post(f"{W}/admin/delivery/test-sms", headers=h, json={"to": "08012345678"}).status_code == 200
    # test mode off and nothing configured -> a clear technical reason for the admin
    web.put(f"{W}/admin/delivery", headers=h, json={"otp_dev_mode": False})
    r = web.post(f"{W}/admin/delivery/test-email", headers=h, json={"to": "me@example.com"})
    assert r.status_code == 502 and "missing SMTP host" in r.json()["detail"]
    ev = web.get(f"{W}/admin/reports/events", headers=h).json()
    changes = [e["detail"] for e in ev if e["event"] == "delivery_settings_changed"]
    assert changes and all("example.com" not in d for d in changes)           # field names are logged, never values


# ---------- ballot lock rules ----------
def test_ballot_lock_follows_open_state_and_votes(web):
    from core import services
    h = admin_headers(web)
    pos = lambda: web.post(f"{W}/admin/positions", json={"title": "Director of Social", "display_order": 4}, headers=h)
    set_status = lambda st: (lambda db: (services.set_status(db, st), db.close()))(SessionLocal())

    set_status("closed")                       # opened and closed in a test, nobody voted: still editable
    assert pos().status_code == 200
    set_status("open")                         # voting open: locked, with the reason
    r = pos()
    assert r.status_code == 409 and "while voting is open" in r.json()["detail"]

    _, r = sign_in(web, W)                     # a vote is cast ...
    h2 = {"Authorization": f"Bearer {r.json()['token']}"}
    assert web.post(f"{W}/vote", json={"selections": ballot_selection(web, r.json()["token"]), **LOC}, headers=h2).status_code == 200
    set_status("closed")                       # ... so even when closed the ballot stays locked
    r = pos()
    assert r.status_code == 409 and "Votes have already been cast" in r.json()["detail"]
    assert web.post(f"{W}/admin/candidates/import", files={"file": ("c.csv", b"position,full_name\nPresident,New Person\n")}, headers=h).status_code == 409


# ---------- the downloadable CSV templates must import cleanly ----------
def _template(name):
    import pathlib
    return (pathlib.Path(__file__).resolve().parents[2] / "web" / "public" / "templates" / name).read_bytes()


def test_students_template_imports(web):
    h = admin_headers(web)
    r = web.post(f"{W}/admin/voters/import", files={"file": ("students_template.csv", _template("students_template.csv"))}, headers=h).json()
    assert len(r["created"]) == 5 and r["skipped"] == []
    assert r["created"][4] == {"matric_no": "MCM/2024/009", "full_name": "Tunde Bello", "has_email": False, "has_phone": True}


def test_candidates_template_imports(web):
    from core import services
    h = admin_headers(web)
    db = SessionLocal()
    services.set_status(db, "draft")
    db.close()
    r = web.post(f"{W}/admin/candidates/import", files={"file": ("candidates_template.csv", _template("candidates_template.csv"))}, headers=h).json()
    assert len(r["created"]) == 5 and r["skipped"] == []
    pos = {p["title"]: p for p in web.get(f"{W}/admin/positions", headers=h).json()}
    names = {c["full_name"] for c in pos["President"]["candidates"]}
    assert names == {"Ada", "Bayo", "Amina Yusuf", "Chidi Okafor"}       # Ada and Bayo come from the test fixture
    assert {"Vice President", "General Secretary", "Director of Sports"} <= set(pos)


def test_twilio_fields_are_validated(web):
    h = admin_headers(web)
    put = lambda **kw: web.put(f"{W}/admin/delivery", headers=h, json={"sms_provider": "twilio", **kw})
    r = put(sms_username="SKexample-api-key-sid")
    assert r.status_code == 400 and "starts with AC" in r.json()["detail"]
    r = put(sms_username="AC" + "a" * 32, sms_sender_id="SUG-Election 2026")
    assert r.status_code == 400 and "Hyphens" in r.json()["detail"]
    assert put(sms_username="AC" + "a" * 32, sms_sender_id="+12025550123", sms_api_key="token").status_code == 200
    assert put(sms_sender_id="MG" + "b" * 32).status_code == 200
    assert put(sms_sender_id="SUGVOTE").status_code == 200
    # other providers are not affected
    assert web.put(f"{W}/admin/delivery", headers=h, json={"sms_provider": "termii", "sms_username": "whatever"}).status_code == 200
