from typing import Literal

from pydantic import BaseModel, Field


class LocationIn(BaseModel):
    """Position reported by the browser / phone. Required when LOCATION_REQUIRED is true."""
    latitude: float | None = None
    longitude: float | None = None
    accuracy_m: float | None = None


class LookupIn(LocationIn):
    matric_no: str = Field(min_length=1, max_length=40)
    device_id: str = Field(default="", max_length=100)


class SendOtpIn(BaseModel):
    session_id: str = Field(min_length=36, max_length=36)
    channel: Literal["email", "sms"]


class VerifyOtpIn(LocationIn):
    session_id: str = Field(min_length=36, max_length=36)
    otp: str = Field(min_length=4, max_length=10)


class AdminLogin(BaseModel):
    username: str
    password: str


class VoteIn(LocationIn):
    selections: dict[int, int]  # {position_id: candidate_id}


class PositionIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    display_order: int = 0


class CandidateIn(BaseModel):
    position_id: int
    full_name: str = Field(min_length=1, max_length=120)
    department: str = ""
    level: str = ""
    manifesto: str = ""
    photo_url: str = ""


class ContactIn(BaseModel):
    email: str = Field(default="", max_length=120)
    phone: str = Field(default="", max_length=30)


class StatusIn(BaseModel):
    status: str  # draft | open | closed


class ResetIn(BaseModel):
    confirm: str


class DeliveryIn(BaseModel):
    """Every field optional: only what is sent is changed. A blank secret keeps the saved one."""
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool | None = None
    sms_provider: str | None = None
    sms_api_key: str | None = None
    sms_username: str | None = None
    sms_sender_id: str | None = None
    default_country_code: str | None = None
    otp_dev_mode: bool | None = None
    otp_ttl_minutes: int | None = None
    otp_max_attempts: int | None = None
    otp_send_limit: int | None = None
    clear_secrets: list[str] = []


class TestSendIn(BaseModel):
    to: str = Field(min_length=3, max_length=120)
