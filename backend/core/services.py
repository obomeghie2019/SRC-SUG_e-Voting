"""Business logic shared by the web API and the mobile API.
Both APIs stay thin; the rules (one vote per voter, ballot lock, results) live here once."""
import secrets
import string
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Admin, Candidate, Position, Setting, Vote, VoteReceipt, Voter
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


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message, self.status = message, status


# ---------- settings ----------
def get_settings(db: Session) -> dict:
    stored = {s.key: s.value for s in db.scalars(select(Setting))}
    return {**DEFAULTS, **stored}


def public_config(db: Session) -> dict:
    s = get_settings(db)
    return {k: s[k] for k in PUBLIC_KEYS}


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
    db.commit()
    set_status(db, "draft")


# ---------- auth ----------
def authenticate_voter(db: Session, matric_no: str, password: str) -> Voter | None:
    v = db.scalar(select(Voter).where(func.lower(Voter.matric_no) == matric_no.strip().lower()))
    if v and v.is_active and verify_pw(password, v.password_hash):
        return v
    return None


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


def cast_vote(db: Session, voter_id: int, selections: dict[int, int], channel: str) -> str:
    if get_settings(db)["election_status"] != "open":
        raise ServiceError("Voting is not open right now", 403)
    voter = db.get(Voter, voter_id)
    if not voter or not voter.is_active:
        raise ServiceError("Account disabled", 403)
    if not selections:
        raise ServiceError("Select at least one candidate")

    positions = {p.id: p for p in db.scalars(select(Position))}
    for pid, cid in selections.items():
        pos = positions.get(pid)
        if not pos or cid not in {c.id for c in pos.candidates}:
            raise ServiceError(f"Invalid selection for position {pid}")

    code = secrets.token_hex(6).upper()
    try:  # receipt + votes commit together or not at all
        db.add(VoteReceipt(voter_id=voter_id, receipt_code=code, channel=channel))
        db.flush()  # unique(voter_id) fires here on a double submit
        db.add_all([Vote(position_id=pid, candidate_id=cid) for pid, cid in selections.items()])
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
    if get_settings(db)["election_status"] != "draft":
        raise ServiceError("Ballot is locked once the election has opened. You can still edit names and details.", 409)


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
def _new_pin() -> str:
    return "".join(secrets.choice(string.digits) for _ in range(6))


def import_voters(db: Session, rows: list[dict]) -> dict:
    existing = {m.lower() for m in db.scalars(select(Voter.matric_no))}
    created, skipped = [], []
    for r in rows:
        matric, name = (r.get("matric_no") or "").strip(), (r.get("full_name") or "").strip()
        if not matric or not name:
            skipped.append({"matric_no": matric, "reason": "missing matric_no or full_name"})
        elif matric.lower() in existing:
            skipped.append({"matric_no": matric, "reason": "already registered"})
        else:
            pin = _new_pin()
            db.add(Voter(matric_no=matric, full_name=name, email=(r.get("email") or "").strip(),
                         department=(r.get("department") or "").strip(), level=(r.get("level") or "").strip(),
                         password_hash=hash_pw(pin)))
            existing.add(matric.lower())
            created.append({"matric_no": matric, "full_name": name, "pin": pin})
    db.commit()
    return {"created": created, "skipped": skipped}


def reset_pin(db: Session, voter_id: int) -> dict:
    v = db.get(Voter, voter_id)
    if not v:
        raise ServiceError("Voter not found", 404)
    pin = _new_pin()
    v.password_hash = hash_pw(pin)
    db.commit()
    return {"matric_no": v.matric_no, "full_name": v.full_name, "pin": pin}


def list_voters(db: Session, q: str = "", limit: int = 200, offset: int = 0) -> dict:
    stmt = select(Voter).order_by(Voter.id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(func.lower(Voter.matric_no).like(like) | func.lower(Voter.full_name).like(like))
    total = db.scalar(select(func.count()).select_from(stmt.subquery()))
    voted_ids = set(db.scalars(select(VoteReceipt.voter_id)))
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    return {"total": total, "voters": [
        {"id": v.id, "matric_no": v.matric_no, "full_name": v.full_name, "department": v.department,
         "level": v.level, "is_active": v.is_active, "has_voted": v.id in voted_ids} for v in rows]}


def set_voter_active(db: Session, voter_id: int, active: bool):
    v = db.get(Voter, voter_id)
    if not v:
        raise ServiceError("Voter not found", 404)
    v.is_active = active
    db.commit()
