"""Voter sign-in flow (shared by the web and mobile APIs).

    1. start_session   matric number + location  -> session id + masked contact options
    2. send_code       session id + email|sms    -> 6-digit code sent to the contact ON RECORD
    3. verify_code     session id + code         -> session becomes 'verified' (caller issues the voting token)
    4. the vote        uses the verified session; afterwards it is marked 'used'

Everything is tied to the session row, so a code cannot be used from a different session,
by a different voter, or on the other app (web vs mobile).
"""
import logging
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from . import audit, config, delivery, geo, notify
from .audit import ClientInfo, aware, utcnow
from .errors import ServiceError
from .models import AuthSession, Voter, VoteReceipt
from .security import hash_pw, verify_pw
from .services import get_settings

log = logging.getLogger("evoting.otp")
OPEN_STATES = ("started", "code_sent", "verified")


def _channels(voter: Voter, cfg) -> list[dict]:
    out = []
    if voter.email and notify.email_ready(cfg):
        out.append({"channel": "email", "masked": notify.mask_email(voter.email)})
    if voter.phone and notify.sms_ready(cfg):
        out.append({"channel": "sms", "masked": notify.mask_phone(voter.phone)})
    return out


def _rate_window():
    return utcnow() - timedelta(minutes=config.OTP_SEND_WINDOW_MINUTES)


def start_session(db: Session, matric_no: str, client: str, info: ClientInfo, device_id: str = "") -> dict:
    geo.require_location(info.latitude, info.longitude)

    status = get_settings(db)["election_status"]
    if status != "open":
        raise ServiceError("Voting has closed." if status == "closed" else "Voting has not started yet.", 403)

    if info.ip and audit.count(db, "lookup_failed", _rate_window(), ip=info.ip) >= config.LOOKUP_FAIL_LIMIT:
        raise ServiceError("Too many unknown matric numbers from this connection. Try again later.", 429)

    voter = db.scalar(select(Voter).where(func.lower(Voter.matric_no) == matric_no.strip().lower()))
    if not voter or not voter.is_active:
        audit.log(db, "lookup_failed", info=info, detail=matric_no.strip()[:40])
        raise ServiceError("No active voter was found with that matric number.", 404)

    if db.scalar(select(VoteReceipt.id).where(VoteReceipt.voter_id == voter.id)) is not None:
        audit.log(db, "lookup_already_voted", voter_id=voter.id, info=info)
        raise ServiceError("You have already voted in this election.", 409)

    if not (voter.email or voter.phone):
        raise ServiceError("No email or phone number is on record for you. Contact the election committee.", 422)
    cfg = delivery.load(db)
    channels = _channels(voter, cfg)
    if not channels:
        # The voter has contacts, but the matching delivery service (SMTP / SMS gateway) is not set up.
        log.error("No code delivery is configured for %s (email ready: %s, SMS ready: %s). Set them in the admin "
                  "Delivery page, or turn on Test mode for local testing.", voter.matric_no, notify.email_ready(cfg), notify.sms_ready(cfg))
        raise ServiceError("Code delivery (email/SMS) is not set up yet. Please contact the election committee.", 503)

    # one live sign-in per voter: a new session cancels the previous one
    db.execute(update(AuthSession).where(AuthSession.voter_id == voter.id, AuthSession.status.in_(OPEN_STATES))
               .values(status="cancelled"))
    s = AuthSession(id=str(uuid.uuid4()), voter_id=voter.id, client=client, status="started",
                    ip=info.ip, user_agent=info.user_agent, device_id=device_id[:100],
                    latitude=info.latitude if info.has_location() else None,
                    longitude=info.longitude if info.has_location() else None, accuracy_m=info.accuracy_m)
    db.add(s)
    db.commit()
    audit.log(db, "lookup_ok", voter_id=voter.id, session_id=s.id, info=info)
    return {"session_id": s.id, "channels": channels, "otp_ttl_minutes": cfg.otp_ttl_minutes}


def _session(db: Session, session_id: str, client: str, allowed: tuple[str, ...]) -> AuthSession:
    s = db.get(AuthSession, session_id)
    if not s or s.client != client:
        raise ServiceError("Sign-in session not found. Start again.", 404)
    if utcnow() - aware(s.created_at) > timedelta(minutes=config.SESSION_MINUTES):
        s.status = "expired"
        db.commit()
    if s.status not in allowed:
        raise ServiceError({
            "expired": "This sign-in session has expired. Start again.",
            "locked": "Too many wrong codes. Start again or contact the election committee.",
            "cancelled": "This sign-in was replaced by a newer one. Start again.",
            "used": "This session has already been used.",
            "started": "Request a code first.",
        }.get(s.status, "Start the sign-in again."), 409)
    return s


def send_code(db: Session, session_id: str, channel: str, client: str, info: ClientInfo) -> dict:
    s = _session(db, session_id, client, ("started", "code_sent"))
    voter = db.get(Voter, s.voter_id)
    cfg = delivery.load(db)
    if channel not in {c["channel"] for c in _channels(voter, cfg)}:
        raise ServiceError("That delivery option is not available for you.", 400)

    since = _rate_window()
    if audit.count(db, "otp_sent", since, voter_id=voter.id) >= cfg.otp_send_limit:
        raise ServiceError(f"Too many codes requested. Wait {config.OTP_SEND_WINDOW_MINUTES} minutes and try again.", 429)
    if info.ip and audit.count(db, "otp_sent", since, ip=info.ip) >= config.OTP_IP_SEND_LIMIT:
        raise ServiceError("Too many codes requested from this connection. Try again later.", 429)

    code = f"{secrets.randbelow(10 ** 6):06d}"
    try:
        notify.deliver(cfg, channel, voter, code, get_settings(db)["institution_name"])
    except ServiceError:
        audit.log(db, "otp_send_failed", voter_id=voter.id, session_id=s.id, info=info, detail=channel)
        raise
    s.otp_hash, s.channel, s.attempts, s.status = hash_pw(code), channel, 0, "code_sent"
    s.otp_expires_at = utcnow() + timedelta(minutes=cfg.otp_ttl_minutes)
    db.commit()
    audit.log(db, "otp_sent", voter_id=voter.id, session_id=s.id, info=info, detail=channel)
    masked = notify.mask_email(voter.email) if channel == "email" else notify.mask_phone(voter.phone)
    return {"sent_to": masked, "channel": channel, "expires_in_seconds": cfg.otp_ttl_minutes * 60}


def verify_code(db: Session, session_id: str, code: str, client: str, info: ClientInfo) -> tuple[Voter, AuthSession]:
    s = _session(db, session_id, client, ("code_sent",))
    if aware(s.otp_expires_at) < utcnow():
        s.status = "expired"
        db.commit()
        raise ServiceError("That code has expired. Request a new one.", 410)

    s.attempts += 1
    if not verify_pw(code.strip(), s.otp_hash):
        left = delivery.load(db).otp_max_attempts - s.attempts
        if left <= 0:
            s.status = "locked"
        db.commit()
        audit.log(db, "otp_failed", voter_id=s.voter_id, session_id=s.id, info=info, detail=f"attempt {s.attempts}")
        raise ServiceError("Incorrect code. " + (f"{left} attempt(s) left." if left > 0 else "Start again."), 401)

    if db.scalar(select(VoteReceipt.id).where(VoteReceipt.voter_id == s.voter_id)) is not None:
        raise ServiceError("You have already voted in this election.", 409)
    s.status, s.otp_hash, s.verified_at = "verified", "", utcnow()
    if info.has_location():  # keep the freshest position
        s.latitude, s.longitude, s.accuracy_m = info.latitude, info.longitude, info.accuracy_m
    s.ip = info.ip or s.ip
    db.commit()
    audit.log(db, "otp_verified", voter_id=s.voter_id, session_id=s.id, info=info, detail=s.channel)
    return db.get(Voter, s.voter_id), s


def assert_verified(db: Session, claims: dict, client: str) -> AuthSession:
    """Guard for /ballot and /vote: the token must point at a live, verified OTP session of the same voter."""
    s = db.get(AuthSession, claims.get("sid", ""))
    if (not s or s.client != client or s.voter_id != int(claims["sub"]) or s.status != "verified"
            or utcnow() - aware(s.verified_at) > timedelta(minutes=config.VOTE_TOKEN_MINUTES)):
        raise ServiceError("Your session has ended. Sign in again.", 401)
    return s
