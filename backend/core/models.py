from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def now():
    return datetime.now(timezone.utc)


class Setting(Base):
    """Key/value system configuration. Read by BOTH the web and mobile APIs."""
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")


class Admin(Base):
    __tablename__ = "admins"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    full_name: Mapped[str] = mapped_column(String(120), default="")
    password_hash: Mapped[str] = mapped_column(String(100))


class Voter(Base):
    __tablename__ = "voters"
    id: Mapped[int] = mapped_column(primary_key=True)
    matric_no: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(120), default="")
    phone: Mapped[str] = mapped_column(String(30), default="")  # international format, e.g. +2348012345678
    department: Mapped[str] = mapped_column(String(120), default="", index=True)
    level: Mapped[str] = mapped_column(String(20), default="", index=True)
    password_hash: Mapped[str] = mapped_column(String(100))  # legacy PIN column; no longer used to sign in
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Position(Base):
    __tablename__ = "positions"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(120))
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="position", cascade="all, delete-orphan", order_by="Candidate.id"
    )


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"))
    full_name: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(120), default="")
    level: Mapped[str] = mapped_column(String(20), default="")
    manifesto: Mapped[str] = mapped_column(Text, default="")
    photo_url: Mapped[str] = mapped_column(String(300), default="")
    position: Mapped[Position] = relationship(back_populates="candidates")


class VoteReceipt(Base):
    """WHO has voted. One row per voter (unique) -> prevents double voting.
    Deliberately has no link to what they voted for."""
    __tablename__ = "vote_receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    voter_id: Mapped[int] = mapped_column(ForeignKey("voters.id"), unique=True)
    receipt_code: Mapped[str] = mapped_column(String(20), unique=True)
    channel: Mapped[str] = mapped_column(String(10), default="web")  # web | mobile
    cast_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    # Forensic evidence captured when the vote was cast (who/where/how, never WHAT)
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Vote(Base):
    """WHAT was voted. Deliberately has no voter_id -> ballot secrecy."""
    __tablename__ = "votes"
    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    cast_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class AuthSession(Base):
    """One sign-in attempt: matric lookup -> channel choice -> OTP. The voting token is bound to this row."""
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid4
    voter_id: Mapped[int] = mapped_column(ForeignKey("voters.id"), index=True)
    client: Mapped[str] = mapped_column(String(10))  # web | mobile
    # started -> code_sent -> verified -> used   (or expired / locked / cancelled)
    status: Mapped[str] = mapped_column(String(12), default="started", index=True)
    channel: Mapped[str] = mapped_column(String(10), default="")  # email | sms
    otp_hash: Mapped[str] = mapped_column(String(100), default="")
    otp_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ip: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")
    device_id: Mapped[str] = mapped_column(String(100), default="")
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Append-only security events: lookups, OTP sends, failures, votes, report views."""
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    event: Mapped[str] = mapped_column(String(40), index=True)
    voter_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # no FK: log outlives voters
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    detail: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
