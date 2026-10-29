"""Business logic shared by the web API and the mobile API.
Both APIs stay thin; the rules (one vote per voter, ballot lock, results) live here once."""
import secrets
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import config, delivery, geo, notify
from .audit import ClientInfo
from .errors import ServiceError  # noqa: F401  (re-exported for the APIs)
from .models import Admin, AuditLog, AuthSession, Candidate, Position, Setting, Vote, VoteReceipt, Voter
from .security import hash_pw, verify_pw

STATUSES = ("draft", "open", "closed")
DEFAULTS = {
    "institution_name": "Your Institution",
    "election_title": "SUG/SRC General Election",
    "election_status": "draft",
    "logo_url": "",
    "theme_color": "#0b6e4f",
    "show_results_to_voters": "false",
}
PUBLIC_KEYS = ("institution_name", "election_title", "election_status", "logo_url", "theme_color")


# ---------- settings ----------
def get_settings(db: Session) -> dict:
    # 'delivery.*' rows hold encrypted SMTP/SMS secrets (core/delivery.py); 'license.*' holds the license state (core/licensing.py)
    stored = {s.key: s.value for s in db.scalars(select(Setting)) if not s.key.startswith((delivery.PREFIX, "license."))}
    return {**DEFAULTS, **stored}


def public_config(db: Session) -> dict:
    s = get_settings(db)
    return {**{k: s[k] for k in PUBLIC_KEYS}, "location_required": config.LOCATION_REQUIRED,
            "otp_ttl_minutes": delivery.load(db).otp_ttl_minutes}


def update_settings(db: Session, data: dict) -> dict:
    for key, value in data.items():
        if key not in DEFAULTS or key == "election_status":  # status has its own guarded endpoint
            continue
        row = db.get(Setting, key)
        if row:
            row.value = str(value)
        else:
            db.add(Setting(key=key, value=str(value)))
    db.commit()
    return get_settings(db)


def set_status(db: Session, status: str) -> dict:
    if status not in STATUSES:
        raise ServiceError("Status must be draft, open or closed")
    if status == "draft" and db.scalar(select(func.count()).select_from(VoteReceipt)):
        raise ServiceError("Votes already exist. Reset the election before returning to draft.")
    row = db.get(Setting, "election_status")
    if row:
        row.value = status
    else:
        db.add(Setting(key="election_status", value=status))
    db.commit()
    return get_settings(db)


def reset_election(db: Session):
    db.query(Vote).delete()
    db.query(VoteReceipt).delete()
    db.query(AuthSession).delete()   # a dry run must not leave sign-in sessions or evidence behind
    db.query(AuditLog).delete()
    db.commit()
    set_status(db, "draft")


# ---------- auth ----------
def authenticate_admin(db: Session, username: str, password: str) -> Admin | None:
    a = db.scalar(select(Admin).where(Admin.username == username.strip()))
    if a and verify_pw(password, a.password_hash):
        return a
    return None


# ---------- ballot & voting ----------
def _candidate_dict(c: Candidate) -> dict:
    return {"id": c.id, "full_name": c.full_name, "department": c.department,
            "level": c.level, "manifesto": c.manifesto, "photo_url": c.photo_url}


def get_ballot(db: Session, voter_id: int) -> dict:
    positions = db.scalars(select(Position).order_by(Position.display_order, Position.id)).all()
    has_voted = db.scalar(select(VoteReceipt.id).where(VoteReceipt.voter_id == voter_id)) is not None
    return {
        "has_voted": has_voted,
        "positions": [
            {"id": p.id, "title": p.title, "candidates": [_candidate_dict(c) for c in p.candidates]}
            for p in positions if p.candidates
        ],
    }


def cast_vote(db: Session, voter_id: int, selections: dict[int, int], channel: str,
              info: ClientInfo | None = None, session: AuthSession | None = None) -> str:
    """Records the receipt (who/where/when) and the votes (what) in ONE transaction.
    The two tables are deliberately not linked, so the forensic report can never reveal a choice."""
    if get_settings(db)["election_status"] != "open":
        raise ServiceError("Voting is not open right now", 403)
    voter = db.get(Voter, voter_id)
    if not voter or not voter.is_active:
        raise ServiceError("Account disabled", 403)
    if not selections:
        raise ServiceError("Select at least one candidate")

    info = info or ClientInfo()
    lat, lng, acc = info.latitude, info.longitude, info.accuracy_m
    if not geo.valid(lat, lng) and session is not None:  # fall back to the position captured at sign-in
        lat, lng, acc = session.latitude, session.longitude, session.accuracy_m
    geo.require_location(lat, lng)

    positions = {p.id: p for p in db.scalars(select(Position))}
    for pid, cid in selections.items():
        pos = positions.get(pid)
        if not pos or cid not in {c.id for c in pos.candidates}:
            raise ServiceError(f"Invalid selection for position {pid}")

    code = secrets.token_hex(6).upper()
    try:  # receipt + votes commit together or not at all
        db.add(VoteReceipt(
            voter_id=voter_id, receipt_code=code, channel=channel,
            session_id=session.id if session else None,
            ip=info.ip or (session.ip if session else None),
            latitude=lat if geo.valid(lat, lng) else None, longitude=lng if geo.valid(lat, lng) else None,
            accuracy_m=acc, user_agent=info.user_agent or (session.user_agent if session else None),
            device_id=(session.device_id or None) if session else None))
        db.flush()  # unique(voter_id) fires here on a double submit
        db.add_all([Vote(position_id=pid, candidate_id=cid) for pid, cid in selections.items()])
        if session is not None:
            session.status = "used"
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ServiceError("You have already voted", 409)
    return code


# ---------- results & analytics ----------
def results(db: Session) -> list[dict]:
    counts = dict(db.execute(select(Vote.candidate_id, func.count()).group_by(Vote.candidate_id)).all())
    out = []
    for p in db.scalars(select(Position).order_by(Position.display_order, Position.id)):
        cands = [{"id": c.id, "full_name": c.full_name, "votes": counts.get(c.id, 0)} for c in p.candidates]
        total = sum(c["votes"] for c in cands)
        for c in cands:
            c["pct"] = round(100 * c["votes"] / total, 1) if total else 0
        out.append({"position_id": p.id, "title": p.title, "total_votes": total,
                    "candidates": sorted(cands, key=lambda c: -c["votes"])})
    return out


def turnout(db: Session) -> dict:
    registered = db.scalar(select(func.count()).select_from(Voter).where(Voter.is_active.is_(True))) or 0
    voted = db.scalar(select(func.count()).select_from(VoteReceipt)) or 0
    return {"registered": registered, "voted": voted,
            "pct": round(100 * voted / registered, 1) if registered else 0}


def live(db: Session) -> dict:
    return {"status": get_settings(db)["election_status"], "turnout": turnout(db), "results": results(db)}


def _breakdown(db: Session, col) -> list[dict]:
    reg = dict(db.execute(select(col, func.count()).select_from(Voter).group_by(col)).all())
    voted = dict(db.execute(
        select(col, func.count()).select_from(VoteReceipt).join(Voter, Voter.id == VoteReceipt.voter_id).group_by(col)
    ).all())
    rows = [{"name": k or "Unspecified", "registered": n, "voted": voted.get(k, 0),
             "pct": round(100 * voted.get(k, 0) / n, 1) if n else 0} for k, n in reg.items()]
    return sorted(rows, key=lambda r: r["name"])


def analytics(db: Session) -> dict:
    buckets: dict[str, int] = defaultdict(int)
    for t in db.scalars(select(VoteReceipt.cast_at)):
        buckets[t.strftime("%Y-%m-%d %H:00")] += 1
    channels = [{"name": c, "value": n} for c, n in
                db.execute(select(VoteReceipt.channel, func.count()).group_by(VoteReceipt.channel)).all()]
    return {
        "turnout": turnout(db),
        "by_department": _breakdown(db, Voter.department),
        "by_level": _breakdown(db, Voter.level),
        "by_channel": channels,
        "timeline": [{"time": k, "votes": v} for k, v in sorted(buckets.items())],
        "results": results(db),
    }


# ---------- admin: ballot setup ----------
def _assert_ballot_unlocked(db: Session):
    """The ballot (positions, candidates, photos) is locked while voting is open, and for good once any vote exists.
    A draft, or a closed election in which nobody voted (for example an open/close test), can still be edited."""
    if get_settings(db)["election_status"] == "open":
        raise ServiceError("The ballot cannot be changed while voting is open. Close voting first.", 409)
    if db.scalar(select(func.count()).select_from(VoteReceipt)):
        raise ServiceError("Votes have already been cast, so the ballot is locked. If they were only test votes, "
                           "go to Settings and use Clear all votes.", 409)


def create_position(db: Session, title: str, display_order: int) -> Position:
    _assert_ballot_unlocked(db)
    p = Position(title=title.strip(), display_order=display_order)
    db.add(p); db.commit()
    return p


def update_position(db: Session, pid: int, title: str, display_order: int) -> Position:
    p = db.get(Position, pid)
    if not p:
        raise ServiceError("Position not found", 404)
    p.title, p.display_order = title.strip(), display_order
    db.commit()
    return p


def delete_position(db: Session, pid: int):
    _assert_ballot_unlocked(db)
    p = db.get(Position, pid)
    if not p:
        raise ServiceError("Position not found", 404)
    db.delete(p); db.commit()


def create_candidate(db: Session, data: dict) -> Candidate:
    _assert_ballot_unlocked(db)
    if not db.get(Position, data["position_id"]):
        raise ServiceError("Position not found", 404)
    c = Candidate(**data)
    db.add(c); db.commit()
    return c


def update_candidate(db: Session, cid: int, data: dict) -> Candidate:
    c = db.get(Candidate, cid)
    if not c:
        raise ServiceError("Candidate not found", 404)
    data.pop("position_id", None)  # moving a candidate between positions is not allowed
    for k, v in data.items():
        setattr(c, k, v)
    db.commit()
    return c


def delete_candidate(db: Session, cid: int):
    _assert_ballot_unlocked(db)
    c = db.get(Candidate, cid)
    if not c:
        raise ServiceError("Candidate not found", 404)
    db.delete(c); db.commit()


def admin_positions(db: Session) -> list[dict]:
    return [{"id": p.id, "title": p.title, "display_order": p.display_order,
             "candidates": [_candidate_dict(c) for c in p.candidates]}
            for p in db.scalars(select(Position).order_by(Position.display_order, Position.id))]


# ---------- admin: voters ----------
def import_voters(db: Session, rows: list[dict]) -> dict:
    """CSV columns: matric_no, full_name, email, phone, department, level.
    New matric numbers are registered; for existing ones a changed email/phone is updated."""
    existing = {v.matric_no.lower(): v for v in db.scalars(select(Voter))}
    cc = delivery.load(db).default_country_code
    created, updated, skipped = [], [], []
    for r in rows:
        matric, name = (r.get("matric_no") or "").strip(), (r.get("full_name") or "").strip()
        email = (r.get("email") or "").strip()
        phone = notify.normalize_phone(r.get("phone") or "", cc)
        if not matric:
            skipped.append({"matric_no": matric, "reason": "missing matric_no"})
        elif email and not notify.valid_email(email):
            skipped.append({"matric_no": matric, "reason": "invalid email"})
        elif matric.lower() in existing:
            v = existing[matric.lower()]
            changed = False
            if email and v.email != email:
                v.email, changed = email, True
            if phone and v.phone != phone:
                v.phone, changed = phone, True
            (updated if changed else skipped).append(
                {"matric_no": matric, **({} if changed else {"reason": "already registered"})})
        elif not name:
            skipped.append({"matric_no": matric, "reason": "missing full_name"})
        else:
            v = Voter(matric_no=matric, full_name=name, email=email, phone=phone,
                      department=(r.get("department") or "").strip(), level=(r.get("level") or "").strip(),
                      password_hash=hash_pw(secrets.token_hex(16)))  # legacy column; sign-in is by OTP only
            db.add(v)
            existing[matric.lower()] = v
            created.append({"matric_no": matric, "full_name": name, "has_email": bool(email), "has_phone": bool(phone)})
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


def update_voter_contact(db: Session, voter_id: int, email: str, phone: str) -> dict:
    v = db.get(Voter, voter_id)
    if not v:
        raise ServiceError("Voter not found", 404)
    email = email.strip()
    if email and not notify.valid_email(email):
        raise ServiceError("That email address is not valid")
    v.email, v.phone = email, notify.normalize_phone(phone, delivery.load(db).default_country_code)
    db.commit()
    return {"email": v.email, "phone": v.phone}


def list_voters(db: Session, q: str = "", limit: int = 200, offset: int = 0) -> dict:
    stmt = select(Voter).order_by(Voter.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Voter.matric_no).like(like) | func.lower(Voter.full_name).like(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    voted_ids = set(db.scalars(select(VoteReceipt.voter_id)))
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return {"total": total, "voters": [
        {"id": v.id, "matric_no": v.matric_no, "full_name": v.full_name, "email": v.email, "phone": v.phone,
         "department": v.department, "level": v.level, "is_active": v.is_active, "has_voted": v.id in voted_ids}
        for v in rows]}


def set_voter_active(db: Session, voter_id: int, active: bool):
    v = db.get(Voter, voter_id)
    if not v:
        raise ServiceError("Voter not found", 404)
    v.is_active = active
    db.commit()


# ---------- admin: bulk candidate upload ----------
def import_candidates(db: Session, rows: list[dict]) -> dict:
    """CSV columns: position, full_name, department, level, manifesto, photo_url.
    Positions that do not exist yet are created. Only allowed while the election is in draft."""
    _assert_ballot_unlocked(db)
    by_title = {p.title.strip().lower(): p for p in db.scalars(select(Position))}
    next_order = (max((p.display_order for p in by_title.values()), default=0)) + 1
    created, skipped = [], []
    for r in rows:
        title, name = (r.get("position") or "").strip(), (r.get("full_name") or "").strip()
        if not title or not name:
            skipped.append({"full_name": name, "reason": "missing position or full_name"})
            continue
        pos = by_title.get(title.lower())
        if pos is None:
            pos = Position(title=title, display_order=next_order)
            next_order += 1
            db.add(pos)
            db.flush()
            by_title[title.lower()] = pos
        if any(c.full_name.strip().lower() == name.lower() for c in pos.candidates):
            skipped.append({"full_name": name, "reason": "already a candidate for this position"})
            continue
        db.add(Candidate(position_id=pos.id, full_name=name, department=(r.get("department") or "").strip(),
                         level=(r.get("level") or "").strip(), manifesto=(r.get("manifesto") or "").strip(),
                         photo_url=(r.get("photo_url") or "").strip()))
        db.flush()
        db.refresh(pos)
        created.append({"position": title, "full_name": name})
    db.commit()
    return {"created": created, "skipped": skipped}


def candidate_for_photo(db: Session, cid: int) -> Candidate:
    """The candidate whose photo is being changed. Photos are part of the ballot, so draft only."""
    _assert_ballot_unlocked(db)
    c = db.get(Candidate, cid)
    if not c:
        raise ServiceError("Candidate not found", 404)
    return c


def candidate_photo_of(db: Session, cid: int) -> str:
    c = db.get(Candidate, cid)
    return c.photo_url if c else ""
