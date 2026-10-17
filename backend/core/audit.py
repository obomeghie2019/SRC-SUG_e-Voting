"""Audit trail + forensic report.

Design choice (Option A): the forensic report proves WHO voted, WHEN, from WHERE (IP, latitude/longitude)
and on WHICH device. It never reveals WHAT they voted for: the votes table has no voter column.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import config, geo
from .models import AuditLog, AuthSession, Voter, VoteReceipt


@dataclass
class ClientInfo:
    ip: str = ""
    user_agent: str = ""
    latitude: float | None = None
    longitude: float | None = None
    accuracy_m: float | None = None

    @classmethod
    def from_request(cls, request: Request, body=None) -> "ClientInfo":
        return cls(
            ip=client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:300],
            latitude=getattr(body, "latitude", None),
            longitude=getattr(body, "longitude", None),
            accuracy_m=getattr(body, "accuracy_m", None),
        )

    def has_location(self) -> bool:
        return geo.valid(self.latitude, self.longitude)


def client_ip(request: Request) -> str:
    """The voter's IP. X-Forwarded-For is only trusted when TRUST_PROXY=true, otherwise it is trivially spoofed."""
    if config.TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()[:64]
    return (request.client.host if request.client else "")[:64]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    """SQLite/MySQL return naive datetimes; everything is stored as UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def log(db: Session, event: str, *, voter_id=None, session_id=None, info: ClientInfo | None = None, detail: str = ""):
    db.add(AuditLog(event=event, voter_id=voter_id, session_id=session_id,
                    ip=info.ip if info else None,
                    latitude=info.latitude if info and info.has_location() else None,
                    longitude=info.longitude if info and info.has_location() else None,
                    detail=detail[:300]))
    db.commit()


def count(db: Session, event: str, since: datetime, *, voter_id=None, ip=None) -> int:
    stmt = select(func.count()).select_from(AuditLog).where(AuditLog.event == event, AuditLog.created_at >= since)
    if voter_id is not None:
        stmt = stmt.where(AuditLog.voter_id == voter_id)
    if ip:
        stmt = stmt.where(AuditLog.ip == ip)
    return db.scalar(stmt) or 0


# ---------- reports (admin) ----------
def forensic_report(db: Session, q: str = "") -> dict:
    stmt = (select(VoteReceipt, Voter, AuthSession.channel)
            .join(Voter, Voter.id == VoteReceipt.voter_id)
            .outerjoin(AuthSession, AuthSession.id == VoteReceipt.session_id)
            .order_by(VoteReceipt.cast_at))
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Voter.matric_no).like(like) | func.lower(Voter.full_name).like(like)
                          | func.lower(func.coalesce(VoteReceipt.ip, "")).like(like))
    found = db.execute(stmt).all()

    ip_voters, dev_voters = Counter(), Counter()
    for r, v, _ in found:
        if r.ip:
            ip_voters[r.ip] += 1
        if r.device_id:
            dev_voters[r.device_id] += 1

    rows = []
    for r, v, otp_channel in found:
        rows.append({
            "receipt_code": r.receipt_code,
            "cast_at": aware(r.cast_at).isoformat() if r.cast_at else None,
            "matric_no": v.matric_no, "full_name": v.full_name, "department": v.department, "level": v.level,
            "email": v.email, "phone": v.phone,
            "app": r.channel, "otp_channel": otp_channel or "",
            "ip": r.ip or "", "latitude": r.latitude, "longitude": r.longitude, "accuracy_m": r.accuracy_m,
            "distance_from_center_m": geo.distance_from_center(r.latitude, r.longitude),
            "device_id": r.device_id or "", "user_agent": r.user_agent or "",
            "shared_ip": bool(r.ip) and ip_voters[r.ip] > 1,
            "shared_device": bool(r.device_id) and dev_voters[r.device_id] > 1,
            "no_location": not geo.valid(r.latitude, r.longitude),
        })

    since_all = datetime(2000, 1, 1, tzinfo=timezone.utc)
    return {
        "summary": {
            "total_votes": len(rows),
            "distinct_ips": len(ip_voters),
            "shared_ip_votes": sum(1 for x in rows if x["shared_ip"]),
            "shared_device_votes": sum(1 for x in rows if x["shared_device"]),
            "votes_without_location": sum(1 for x in rows if x["no_location"]),
            "failed_otp_attempts": count(db, "otp_failed", since_all),
            "failed_lookups": count(db, "lookup_failed", since_all),
            "geofence_enabled": geo.geofence_enabled(),
        },
        "rows": rows,
    }


def events(db: Session, limit: int = 200, offset: int = 0, event: str = "") -> list[dict]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
    if event:
        stmt = stmt.where(AuditLog.event == event)
    voters = {v.id: v.matric_no for v in db.scalars(select(Voter))}
    return [{"id": e.id, "event": e.event, "matric_no": voters.get(e.voter_id, ""), "ip": e.ip or "",
             "latitude": e.latitude, "longitude": e.longitude, "detail": e.detail,
             "at": aware(e.created_at).isoformat() if e.created_at else None}
            for e in db.scalars(stmt)]
