from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
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
    department: Mapped[str] = mapped_column(String(120), default="", index=True)
    level: Mapped[str] = mapped_column(String(20), default="", index=True)
    password_hash: Mapped[str] = mapped_column(String(100))
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


class Vote(Base):
    """WHAT was voted. Deliberately has no voter_id -> ballot secrecy."""
    __tablename__ = "votes"
    id: Mapped[int] = mapped_column(primary_key=True)
    position_id: Mapped[int] = mapped_column(ForeignKey("positions.id"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"), index=True)
    cast_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
