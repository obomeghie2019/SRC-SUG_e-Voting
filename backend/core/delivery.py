"""Email (SMTP), SMS provider and one-time-code rules that the admin can change from the dashboard.

Stored in the settings table as 'delivery.<name>'. A saved value overrides the .env value; anything never
saved falls back to .env. Secrets (SMTP password, SMS API key) are encrypted with a key derived from
JWT_SECRET and are never sent back to the browser. If JWT_SECRET is changed, saved secrets can no longer be
read and must be entered again.
"""
import base64
import hashlib
import re
from dataclasses import asdict, dataclass

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import config
from .errors import ServiceError
from .models import Setting

PREFIX = "delivery."
SECRET_FIELDS = ("smtp_password", "sms_api_key")
PROVIDERS = ("", "termii", "africastalking", "twilio")


@dataclass
class DeliveryConfig:
    smtp_host: str
    smtp_port: int
    smtp_user: str
    smtp_password: str
    smtp_from: str
    smtp_starttls: bool
    sms_provider: str
    sms_api_key: str
    sms_username: str
    sms_sender_id: str
    default_country_code: str
    otp_dev_mode: bool
    otp_ttl_minutes: int
    otp_max_attempts: int
    otp_send_limit: int


def _env() -> DeliveryConfig:
    return DeliveryConfig(
        smtp_host=config.SMTP_HOST, smtp_port=config.SMTP_PORT, smtp_user=config.SMTP_USER,
        smtp_password=config.SMTP_PASSWORD, smtp_from=config.SMTP_FROM, smtp_starttls=config.SMTP_STARTTLS,
        sms_provider=config.SMS_PROVIDER, sms_api_key=config.SMS_API_KEY, sms_username=config.SMS_USERNAME,
        sms_sender_id=config.SMS_SENDER_ID, default_country_code=config.DEFAULT_COUNTRY_CODE,
        otp_dev_mode=config.OTP_DEV_MODE, otp_ttl_minutes=config.OTP_TTL_MINUTES,
        otp_max_attempts=config.OTP_MAX_ATTEMPTS, otp_send_limit=config.OTP_SEND_LIMIT)


# ---------- secret encryption ----------
def _fernet() -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256((config.JWT_SECRET + "|delivery").encode()).digest()))


def _encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ""


def _decrypt(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode() if value else ""
    except InvalidToken:
        return ""


# ---------- load / view ----------
def _stored(db: Session) -> dict[str, str]:
    rows = db.scalars(select(Setting).where(Setting.key.like(PREFIX + "%"))).all()
    return {r.key[len(PREFIX):]: r.value for r in rows}


def _decode(base: DeliveryConfig, name: str, raw: str):
    current = getattr(base, name)
    if name in SECRET_FIELDS:
        return _decrypt(raw)
    if isinstance(current, bool):
        return raw == "true"
    if isinstance(current, int):
        try:
            return int(raw)
        except ValueError:
            return current
    return raw


def load(db: Session) -> DeliveryConfig:
    base = _env()
    values = asdict(base)
    for name, raw in _stored(db).items():
        if name in values:
            values[name] = _decode(base, name, raw)
    return DeliveryConfig(**values)


# ---------- readiness ----------
def email_missing(cfg: DeliveryConfig) -> list[str]:
    return [label for label, v in (("SMTP host", cfg.smtp_host), ("From address", cfg.smtp_from)) if not v]


def sms_missing(cfg: DeliveryConfig) -> list[str]:
    need = {"termii": (("API key", cfg.sms_api_key), ("Sender ID", cfg.sms_sender_id)),
            "africastalking": (("API key", cfg.sms_api_key), ("Username", cfg.sms_username)),
            "twilio": (("Auth token", cfg.sms_api_key), ("Account SID", cfg.sms_username), ("From number", cfg.sms_sender_id))}
    if cfg.sms_provider not in need:
        return ["SMS provider"]
    return [label for label, v in need[cfg.sms_provider] if not v]


def email_ready(cfg: DeliveryConfig) -> bool:
    return cfg.otp_dev_mode or not email_missing(cfg)


def sms_ready(cfg: DeliveryConfig) -> bool:
    return cfg.otp_dev_mode or not sms_missing(cfg)


def view(db: Session) -> dict:
    """What the dashboard shows. Secrets are never included, only whether one is saved."""
    cfg = load(db)
    stored = _stored(db)
    data = {k: v for k, v in asdict(cfg).items() if k not in SECRET_FIELDS}
    return {
        **data,
        "secrets_set": {k: bool(getattr(cfg, k)) for k in SECRET_FIELDS},
        "sources": {k: ("dashboard" if k in stored else "env") for k in asdict(cfg)},
        "readiness": {
            "test_mode": cfg.otp_dev_mode,
            "email": {"ready": email_ready(cfg), "missing": [] if cfg.otp_dev_mode else email_missing(cfg)},
            "sms": {"ready": sms_ready(cfg), "missing": [] if cfg.otp_dev_mode else sms_missing(cfg)},
        },
    }


# ---------- save ----------
def _int(name: str, v, lo: int, hi: int) -> int:
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ServiceError(f"{name} must be a whole number")
    if not lo <= n <= hi:
        raise ServiceError(f"{name} must be between {lo} and {hi}")
    return n


_ALNUM_SENDER = re.compile(r"^[A-Za-z0-9 ]{1,11}$")


def _check_twilio(provider: str, username: str | None, sender: str | None):
    """Catch the usual Twilio mistakes at save time instead of failing later with a vague error."""
    if provider != "twilio":
        return
    if username and not username.startswith("AC"):
        raise ServiceError("A Twilio Account SID starts with AC. A value starting with SK is an API key, not the Account SID "
                           "(find the Account SID and Auth token on the Twilio console home page).")
    if sender and not (re.fullmatch(r"\+\d{8,15}", sender) or re.fullmatch(r"MG[0-9a-fA-F]{32}", sender)
                       or _ALNUM_SENDER.match(sender)):
        raise ServiceError("Twilio 'From' must be your Twilio phone number (like +12025550123), a Messaging Service SID "
                           "(starts with MG), or an approved alphanumeric sender of up to 11 letters or digits. "
                           "Hyphens and long names are not allowed.")


def save(db: Session, data: dict, clear_secrets: list[str] | None = None) -> list[str]:
    """Validate and store the submitted fields. A blank secret keeps the saved one; add its name to
    clear_secrets to delete it. Returns the field names that were changed (never their values)."""
    provider = str(data.get("sms_provider", load(db).sms_provider) or "").strip().lower()
    _check_twilio(provider, str(data["sms_username"]).strip() if data.get("sms_username") else None,
                  str(data["sms_sender_id"]).strip() if data.get("sms_sender_id") else None)
    clean: dict[str, str] = {}
    for name, v in data.items():
        if name in SECRET_FIELDS:
            if v:
                clean[name] = _encrypt(str(v).strip())
            continue
        if name == "smtp_port":
            clean[name] = str(_int("SMTP port", v, 1, 65535))
        elif name == "otp_ttl_minutes":
            clean[name] = str(_int("Code expiry", v, 1, 30))
        elif name == "otp_max_attempts":
            clean[name] = str(_int("Wrong-code attempts", v, 1, 10))
        elif name == "otp_send_limit":
            clean[name] = str(_int("Codes per voter", v, 1, 20))
        elif name in ("smtp_starttls", "otp_dev_mode"):
            clean[name] = "true" if v in (True, "true", "True", 1) else "false"
        elif name == "sms_provider":
            v = str(v or "").strip().lower()
            if v not in PROVIDERS:
                raise ServiceError("Choose Termii, Africa's Talking, Twilio, or None")
            clean[name] = v
        elif name == "default_country_code":
            v = str(v or "").strip().lstrip("+")
            if not v.isdigit() or not 1 <= len(v) <= 4:
                raise ServiceError("Country code must be 1 to 4 digits, e.g. 234")
            clean[name] = v
        elif name in ("smtp_host", "smtp_user", "smtp_from", "sms_username", "sms_sender_id"):
            clean[name] = str(v or "").strip()[:200]
    for name in clear_secrets or []:
        if name in SECRET_FIELDS:
            clean[name] = ""
    for name, value in clean.items():
        row = db.get(Setting, PREFIX + name)
        if row:
            row.value = value
        else:
            db.add(Setting(key=PREFIX + name, value=value))
    db.commit()
    return sorted(clean)
