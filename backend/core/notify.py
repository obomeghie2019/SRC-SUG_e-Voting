"""Delivers one-time codes by email (SMTP) or SMS (Termii, Africa's Talking or Twilio).

The code is only ever sent to the address / number already stored for the voter.
With OTP_DEV_MODE=true nothing is sent: the code is printed in the API console for local testing.
"""
import logging
import re
import smtplib
import ssl
from email.message import EmailMessage

import httpx

from . import config, delivery
from .errors import ServiceError

log = logging.getLogger("evoting.notify")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_phone(raw: str, cc: str | None = None) -> str:
    """'0801 234 5678' -> '+2348012345678' (country code from Delivery settings / DEFAULT_COUNTRY_CODE)."""
    p = re.sub(r"[^\d+]", "", raw or "")
    if not p:
        return ""
    if p.startswith("+"):
        return p
    if p.startswith("00"):
        return "+" + p[2:]
    cc = cc or config.DEFAULT_COUNTRY_CODE
    if p.startswith("0"):
        return f"+{cc}{p[1:]}"
    if p.startswith(cc) and len(p) > 10:
        return "+" + p
    return f"+{cc}{p}"


def valid_email(e: str) -> bool:
    return bool(EMAIL_RE.match((e or "").strip()))


def mask_email(e: str) -> str:
    local, _, domain = e.partition("@")
    return f"{local[:1]}***@{domain}"


def mask_phone(p: str) -> str:
    return p[:4] + "*" * max(len(p) - 7, 3) + p[-3:]


class DeliveryError(Exception):
    """public: safe to show a voter. technical: shown only to an admin running a test."""

    def __init__(self, public: str, technical: str = "", status: int = 502):
        super().__init__(public)
        self.public, self.technical, self.status = public, technical or public, status


def email_ready(cfg) -> bool:
    return delivery.email_ready(cfg)


def sms_ready(cfg) -> bool:
    return delivery.sms_ready(cfg)


def deliver(cfg, channel: str, voter, code: str, institution: str):
    text = (f"{institution}: your voting code is {code}. It expires in {cfg.otp_ttl_minutes} minutes. "
            "Do not share it with anyone.")
    if cfg.otp_dev_mode:
        print(f"[DEV OTP] {voter.matric_no} via {channel}: {code}", flush=True)
        return
    try:
        if channel == "email":
            _send_email(cfg, voter.email, f"{institution} voting code", text)
        elif channel == "sms":
            _send_sms(cfg, voter.phone, text)
        else:
            raise ServiceError("Unknown delivery channel")
    except DeliveryError as e:
        raise ServiceError(e.public, e.status)


def send_test(cfg, channel: str, to: str, institution: str) -> str:
    """Admin 'send a test' button. Returns a success message or raises ServiceError with the technical reason."""
    text = f"{institution}: this is a test message from the e-voting system. No action is needed."
    if channel == "email":
        if not valid_email(to):
            raise ServiceError("Enter a valid email address")
    else:
        to = normalize_phone(to, cfg.default_country_code)
        if len(to) < 8:
            raise ServiceError("Enter a valid phone number")
    if cfg.otp_dev_mode:
        print(f"[DEV TEST] {channel} test to {to}: {text}", flush=True)
        return "Test mode is ON, so nothing was sent. The message was printed in the server console."
    try:
        if channel == "email":
            _send_email(cfg, to, f"{institution} test email", text)
        else:
            _send_sms(cfg, to, text)
    except DeliveryError as e:
        raise ServiceError(e.technical, 502)
    return f"Test {'email' if channel == 'email' else 'SMS'} sent to {to}."


def _send_email(cfg, to: str, subject: str, body: str):
    if delivery.email_missing(cfg):
        raise DeliveryError("Email delivery is not configured. Choose SMS or contact the election committee.",
                            "Email is not configured: missing " + ", ".join(delivery.email_missing(cfg)), 503)
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg.smtp_from, to, subject
    msg.set_content(body)
    try:
        if cfg.smtp_port == 465:
            smtp = smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=15, context=ssl.create_default_context())
        else:
            smtp = smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15)
            if cfg.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
        with smtp:
            if cfg.smtp_user:
                smtp.login(cfg.smtp_user, cfg.smtp_password)
            smtp.send_message(msg)
    except Exception as exc:  # network, auth or recipient errors
        log.error("Email delivery failed: %s", exc)
        raise DeliveryError("Could not send the email. Try SMS or contact the election committee.",
                            f"{type(exc).__name__}: {str(exc)[:200]}")


def _send_sms(cfg, to: str, text: str):
    if delivery.sms_missing(cfg):
        raise DeliveryError("SMS delivery is not configured. Choose email or contact the election committee.",
                            "SMS is not configured: missing " + ", ".join(delivery.sms_missing(cfg)), 503)
    p = cfg.sms_provider
    try:
        with httpx.Client(timeout=15) as http:
            if p == "termii":
                r = http.post("https://api.ng.termii.com/api/sms/send", json={
                    "to": to.lstrip("+"), "from": cfg.sms_sender_id, "sms": text,
                    "type": "plain", "channel": "generic", "api_key": cfg.sms_api_key})
            elif p == "africastalking":
                r = http.post("https://api.africastalking.com/version1/messaging",
                              headers={"apiKey": cfg.sms_api_key, "Accept": "application/json"},
                              data={"username": cfg.sms_username, "to": to, "message": text,
                                    **({"from": cfg.sms_sender_id} if cfg.sms_sender_id else {})})
            else:  # twilio
                r = http.post(f"https://api.twilio.com/2010-04-01/Accounts/{cfg.sms_username}/Messages.json",
                              auth=(cfg.sms_username, cfg.sms_api_key),
                              data={"To": to, "From": cfg.sms_sender_id, "Body": text})
        r.raise_for_status()
    except httpx.HTTPStatusError as exc:
        log.error("SMS delivery failed (%s): %s", p, exc)
        raise DeliveryError("Could not send the SMS. Try email or contact the election committee.",
                            f"{p} answered HTTP {exc.response.status_code}: {exc.response.text[:160]}")
    except Exception as exc:
        log.error("SMS delivery failed (%s): %s", p, exc)
        raise DeliveryError("Could not send the SMS. Try email or contact the election committee.",
                            f"{type(exc).__name__}: {str(exc)[:200]}")
