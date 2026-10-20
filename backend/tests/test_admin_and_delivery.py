"""Admin CRUD, reports, geo rules, schema upgrade and the email/SMS senders (with the network faked)."""
import dataclasses
import types

import httpx
import pytest

from core import config, delivery, geo, notify
from core.db import SessionLocal
from core.errors import ServiceError
from tests.conftest import LOC, REAL_DELIVER, sign_in

W = "/api/web"
VOTER = types.SimpleNamespace(matric_no="T/001", email="one@example.com", phone="+2348011111111")


def admin_headers(web):
    t = web.post(f"{W}/auth/admin/login", json={"username": "admin", "password": "secret-admin"}).json()["token"]
    return {"Authorization": f"Bearer {t}"}


def live_cfg(**kw):
    """A delivery config with test mode OFF so the real senders run (against fakes)."""
    return dataclasses.replace(delivery._env(), otp_dev_mode=False, **kw)


# ---------------- fakes for the network ----------------
class FakeSMTP:
    sent, instances, fail = [], [], False

    def __init__(self, host, port, timeout=0, context=None):
        self.host, self.port, self.tls, self.login_args = host, port, False, None
        FakeSMTP.instances.append(self)

    def starttls(self, context=None):
        self.tls = True

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, msg):
        if FakeSMTP.fail:
            raise OSError("connection refused")
        FakeSMTP.sent.append(msg)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeHttp:
    calls, status = [], 200

    def __init__(self, timeout=0):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, **kw):
        FakeHttp.calls.append((url, kw))
        return httpx.Response(FakeHttp.status, text='{"code":572006}', request=httpx.Request("POST", url))


@pytest.fixture
def net(monkeypatch):
    FakeSMTP.sent, FakeSMTP.instances, FakeSMTP.fail = [], [], False
    FakeHttp.calls, FakeHttp.status = [], 200
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(notify.smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(notify.httpx, "Client", FakeHttp)


# ---------------- notify: email ----------------
def test_email_is_sent_with_login_and_starttls(net):
    cfg = live_cfg(smtp_host="smtp.example.com", smtp_port=587, smtp_user="u", smtp_password="p", smtp_from="v@school.ng", smtp_starttls=True)
    REAL_DELIVER(cfg, "email", VOTER, "123456", "Auchi Poly")
    msg = FakeSMTP.sent[0]
    assert msg["To"] == "one@example.com" and "123456" in msg.get_content() and "Auchi Poly" in msg["Subject"]
    assert FakeSMTP.instances[0].tls and FakeSMTP.instances[0].login_args == ("u", "p")


def test_email_port_465_uses_ssl_and_failures_are_reported(net):
    cfg = live_cfg(smtp_host="smtp.example.com", smtp_port=465, smtp_from="v@school.ng")
    REAL_DELIVER(cfg, "email", VOTER, "111111", "X")
    assert FakeSMTP.instances[0].port == 465 and FakeSMTP.instances[0].login_args is None
    FakeSMTP.fail = True
    with pytest.raises(ServiceError) as e:
        REAL_DELIVER(cfg, "email", VOTER, "111111", "X")
    assert e.value.status == 502 and "Could not send the email" in e.value.message
    with pytest.raises(ServiceError) as e:                       # the admin test shows the technical reason
        notify.send_test(cfg, "email", "me@example.com", "X")
    assert "OSError" in e.value.message


def test_email_not_configured(net):
    with pytest.raises(ServiceError) as e:
        REAL_DELIVER(live_cfg(smtp_host="", smtp_from=""), "email", VOTER, "1", "X")
    assert e.value.status == 503


# ---------------- notify: SMS providers ----------------
def test_termii_request(net):
    cfg = live_cfg(sms_provider="termii", sms_api_key="K", sms_sender_id="SCHOOL")
    REAL_DELIVER(cfg, "sms", VOTER, "654321", "X")
    url, kw = FakeHttp.calls[0]
    assert "termii" in url and kw["json"]["to"] == "2348011111111" and kw["json"]["api_key"] == "K" and "654321" in kw["json"]["sms"]


def test_africastalking_request(net):
    cfg = live_cfg(sms_provider="africastalking", sms_api_key="K", sms_username="app", sms_sender_id="SCHOOL")
    REAL_DELIVER(cfg, "sms", VOTER, "654321", "X")
    url, kw = FakeHttp.calls[0]
    assert "africastalking" in url and kw["headers"]["apiKey"] == "K" and kw["data"]["to"] == "+2348011111111" and kw["data"]["from"] == "SCHOOL"


def test_twilio_number_and_messaging_service(net):
    cfg = live_cfg(sms_provider="twilio", sms_api_key="tok", sms_username="AC" + "a" * 32, sms_sender_id="+12025550123")
    REAL_DELIVER(cfg, "sms", VOTER, "654321", "X")
    url, kw = FakeHttp.calls[0]
    assert "Accounts/AC" in url and kw["auth"] == ("AC" + "a" * 32, "tok") and kw["data"]["From"] == "+12025550123"
    REAL_DELIVER(dataclasses.replace(cfg, sms_sender_id="MG" + "b" * 32), "sms", VOTER, "654321", "X")
    data = FakeHttp.calls[1][1]["data"]
    assert data["MessagingServiceSid"].startswith("MG") and "From" not in data


def test_sms_provider_error_is_explained_to_admin_but_not_voter(net):
    cfg = live_cfg(sms_provider="twilio", sms_api_key="tok", sms_username="AC" + "a" * 32, sms_sender_id="+12025550123")
    FakeHttp.status = 400
    with pytest.raises(ServiceError) as voter_err:
        REAL_DELIVER(cfg, "sms", VOTER, "1", "X")
    assert "572006" not in voter_err.value.message
    with pytest.raises(ServiceError) as admin_err:
        notify.send_test(cfg, "sms", "08012345678", "X")
    assert "twilio answered HTTP 400" in admin_err.value.message and "572006" in admin_err.value.message


def test_sms_not_configured_and_unknown_channel(net):
    with pytest.raises(ServiceError) as e:
        REAL_DELIVER(live_cfg(sms_provider=""), "sms", VOTER, "1", "X")
    assert e.value.status == 503
    with pytest.raises(ServiceError):
        REAL_DELIVER(live_cfg(), "pigeon", VOTER, "1", "X")


def test_phone_normalising_and_masking():
    assert notify.normalize_phone("0801 234 5678") == "+2348012345678"
    assert notify.normalize_phone("+2348012345678") == "+2348012345678"
    assert notify.normalize_phone("2348012345678") == "+2348012345678"
    assert notify.normalize_phone("8012345678") == "+2348012345678"
    assert notify.normalize_phone("0044 7700 900123") == "+447700900123"
    assert notify.normalize_phone("") == "" and notify.normalize_phone("0801", cc="44") == "+44801"
    assert notify.mask_email("amina@x.com") == "a***@x.com" and notify.mask_phone("+2348012345678").endswith("678")


# ---------------- geo ----------------
def test_geo_rules(monkeypatch):
    assert geo.valid(6.5, 3.4) and not geo.valid(0, 0) and not geo.valid(91, 0) and not geo.valid(None, None)
    assert geo.distance_m(6.5, 3.4, 6.5, 3.4) == 0 and 1000 < geo.distance_m(6.5, 3.4, 6.5, 3.41) < 1200
    assert geo.distance_from_center(6.5, 3.4) is None                      # geofence off
    monkeypatch.setattr(config, "GEOFENCE_LAT", 6.5244)
    monkeypatch.setattr(config, "GEOFENCE_LNG", 3.3792)
    monkeypatch.setattr(config, "GEOFENCE_RADIUS_M", 500.0)
    geo.require_location(6.5245, 3.3793)                                    # inside
    with pytest.raises(ServiceError) as e:
        geo.require_location(7.0, 3.9)
    assert e.value.status == 403
    monkeypatch.setattr(config, "LOCATION_REQUIRED", False)
    geo.require_location(None, None)                                        # optional when not required


def test_geofence_blocks_sign_in_outside_area(web, monkeypatch):
    monkeypatch.setattr(config, "GEOFENCE_LAT", 6.5244)
    monkeypatch.setattr(config, "GEOFENCE_LNG", 3.3792)
    monkeypatch.setattr(config, "GEOFENCE_RADIUS_M", 500.0)
    r = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", "latitude": 9.0, "longitude": 7.0})
    assert r.status_code == 403 and "outside" in r.json()["detail"]
    assert web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC}).status_code == 200


# ---------------- admin CRUD, status, reports ----------------
def test_settings_status_and_reset(web):
    h = admin_headers(web)
    assert web.put(f"{W}/admin/settings", json={"institution_name": "Auchi Poly", "election_status": "closed", "bogus": "x"}, headers=h).json()["institution_name"] == "Auchi Poly"
    assert web.get(f"{W}/config").json()["election_status"] == "open"        # status cannot be changed through settings
    assert web.post(f"{W}/admin/election/status", json={"status": "weird"}, headers=h).status_code == 400
    assert web.post(f"{W}/admin/election/status", json={"status": "closed"}, headers=h).status_code == 200
    r = web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC})   # voting is closed, so sign-in is refused
    assert r.status_code == 403 and "closed" in r.json()["detail"]
    assert web.post(f"{W}/admin/election/reset", json={"confirm": "no"}, headers=h).status_code == 400
    assert web.post(f"{W}/admin/election/reset", json={"confirm": "RESET"}, headers=h).status_code == 200
    assert web.get(f"{W}/config").json()["election_status"] == "draft"


def test_cannot_return_to_draft_after_votes(web):
    h = admin_headers(web)
    _, r = sign_in(web, W)
    t = r.json()["token"]
    sel = web.get(f"{W}/ballot", headers={"Authorization": f"Bearer {t}"}).json()["positions"][0]
    assert web.post(f"{W}/vote", json={"selections": {str(sel["id"]): sel["candidates"][0]["id"]}, **LOC}, headers={"Authorization": f"Bearer {t}"}).status_code == 200
    assert web.post(f"{W}/admin/election/status", json={"status": "draft"}, headers=h).status_code == 400


def test_positions_and_candidates_crud(web):
    h = admin_headers(web)
    web.post(f"{W}/admin/election/status", json={"status": "draft"}, headers=h)
    pid = web.post(f"{W}/admin/positions", json={"title": " Treasurer ", "display_order": 2}, headers=h).json()["id"]
    assert web.put(f"{W}/admin/positions/{pid}", json={"title": "Financial Secretary", "display_order": 3}, headers=h).status_code == 200
    assert web.put(f"{W}/admin/positions/9999", json={"title": "x", "display_order": 1}, headers=h).status_code == 404
    cid = web.post(f"{W}/admin/candidates", json={"position_id": pid, "full_name": "Zainab", "department": "CS"}, headers=h).json()["id"]
    assert web.post(f"{W}/admin/candidates", json={"position_id": 9999, "full_name": "Nobody"}, headers=h).status_code == 404
    assert web.put(f"{W}/admin/candidates/{cid}", json={"position_id": pid, "full_name": "Zainab A.", "level": "ND2"}, headers=h).status_code == 200
    assert web.put(f"{W}/admin/candidates/9999", json={"position_id": pid, "full_name": "x"}, headers=h).status_code == 404
    listing = {p["title"]: p for p in web.get(f"{W}/admin/positions", headers=h).json()}
    assert listing["Financial Secretary"]["candidates"][0]["full_name"] == "Zainab A."
    assert web.delete(f"{W}/admin/candidates/{cid}", headers=h).status_code == 200
    assert web.delete(f"{W}/admin/candidates/{cid}", headers=h).status_code == 404
    assert web.delete(f"{W}/admin/positions/{pid}", headers=h).status_code == 200
    assert web.delete(f"{W}/admin/positions/{pid}", headers=h).status_code == 404


def test_voters_listing_contact_and_disable(web):
    h = admin_headers(web)
    listing = web.get(f"{W}/admin/voters", params={"q": "one"}, headers=h).json()
    assert listing["total"] == 1 and listing["voters"][0]["matric_no"] == "T/001"
    vid = listing["voters"][0]["id"]
    assert web.put(f"{W}/admin/voters/{vid}/contact", json={"email": "bad", "phone": ""}, headers=h).status_code == 400
    assert web.put(f"{W}/admin/voters/{vid}/contact", json={"email": "new@example.com", "phone": "07099998888"}, headers=h).json() == {"email": "new@example.com", "phone": "+2347099998888"}
    assert web.put(f"{W}/admin/voters/9999/contact", json={"email": "", "phone": ""}, headers=h).status_code == 404
    assert web.post(f"{W}/admin/voters/{vid}/active", params={"active": "false"}, headers=h).status_code == 200
    assert web.post(f"{W}/auth/lookup", json={"matric_no": "T/001", **LOC}).status_code == 404   # disabled voters cannot sign in
    assert web.post(f"{W}/admin/voters/9999/active", params={"active": "true"}, headers=h).status_code == 404


def test_live_analytics_and_report_filters(web):
    h = admin_headers(web)
    _, r = sign_in(web, W)
    t = r.json()["token"]
    sel = web.get(f"{W}/ballot", headers={"Authorization": f"Bearer {t}"}).json()["positions"][0]
    web.post(f"{W}/vote", json={"selections": {str(sel["id"]): sel["candidates"][0]["id"]}, **LOC}, headers={"Authorization": f"Bearer {t}"})
    live = web.get(f"{W}/admin/live", headers=h).json()
    assert live["turnout"]["voted"] == 1 and live["results"][0]["total_votes"] == 1
    an = web.get(f"{W}/admin/analytics", headers=h).json()
    assert an["by_channel"][0]["name"] == "web" and len(an["timeline"]) == 1
    assert len(web.get(f"{W}/admin/reports/forensic", params={"q": "t/001"}, headers=h).json()["rows"]) == 1
    assert web.get(f"{W}/admin/reports/forensic", params={"q": "nobody"}, headers=h).json()["rows"] == []
    ev = web.get(f"{W}/admin/reports/events", params={"event": "vote_cast"}, headers=h).json()
    assert [e["event"] for e in ev] == ["vote_cast"]


def test_mobile_me_and_results(web, mobile):
    h = admin_headers(web)
    _, r = sign_in(mobile, "/api/mobile", matric="T/001")
    mh = {"Authorization": f"Bearer {r.json()['token']}"}
    assert mobile.get("/api/mobile/me", headers=mh).json()["matric_no"] == "T/001"
    assert mobile.get("/api/mobile/results", headers=mh).status_code == 403          # not published
    web.post(f"{W}/admin/election/status", json={"status": "closed"}, headers=h)
    web.put(f"{W}/admin/settings", json={"show_results_to_voters": "true"}, headers=h)
    assert mobile.get("/api/mobile/results", headers=mh).status_code == 200
    assert mobile.get("/api/mobile/config").json()["location_required"] is True


# ---------------- schema upgrade ----------------
def test_migration_adds_missing_columns(tmp_path):
    import sqlite3

    from sqlalchemy import create_engine, inspect

    from core import migrate
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.executescript("CREATE TABLE voters (id INTEGER PRIMARY KEY, matric_no VARCHAR(40));"
                      "CREATE TABLE vote_receipts (id INTEGER PRIMARY KEY, voter_id INTEGER);")
    con.commit()
    con.close()
    engine = create_engine(f"sqlite:///{path}")
    added = migrate.apply(engine)
    assert "voters.phone" in added and "vote_receipts.ip" in added
    assert {c["name"] for c in inspect(engine).get_columns("voters")} >= {"phone"}
    assert migrate.apply(engine) == []                                                # safe to repeat
