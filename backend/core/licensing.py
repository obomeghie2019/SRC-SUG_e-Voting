"""License seal: a signed license.bat in the project root must be present, unmodified and unexpired.

Same idea as a PHP "license.dat + secret key" check, with the weak points removed:
  * Ed25519 signature instead of md5(expiry + shared secret). The app only holds the PUBLIC key, so a license
    cannot be forged from the application files. Only the holder of the private key can issue one.
  * Plain text fields parsed by hand instead of unserialize() (which can run attacker-controlled code).
  * Every line of the file is covered by the signature, so changing, adding or removing ANY line breaks it.
  * The file is only ever READ as text. It is never executed by the application.
  * Deleting or editing the file triggers a HARD LOCK that only the vendor can lift: with a signed unlock code, or
    by issuing a brand-new license file (see MAX_STRIKES for a more forgiving setting).
  * A clock set back below the last time the app ran is detected.

Nothing here deletes or damages data. A failed check only blocks the application.
Be aware that anyone who controls the server AND the source code can edit the check out of the code. This deters
casual tampering and expiry dodging; it is not copy protection against a determined administrator.
"""
import base64
import json
import re
import secrets
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from sqlalchemy.orm import Session

from . import audit, config
from .errors import ServiceError
from .license_public import PUBLIC_KEY_B64
from .models import Setting

PRODUCT = "SUG/SRC e-Voting System"
STATE_PREFIX = "license."
STATE_KEY = STATE_PREFIX + "state"
SIGNATURE_PREFIX = "REM SIGNATURE:"
UNLOCK_CONTEXT = "EVOTING-UNLOCK:"
# How many delete/edit incidents are allowed before the HARD LOCK. 1 = strict: the first time the license file is
# deleted or changed, the application locks and only the vendor (holder of the private key) can open it again.
# Set to 3 for a forgiving version in which the first two incidents recover when the original file is put back.
MAX_STRIKES = 1
CLOCK_TOLERANCE = timedelta(days=1)               # how far the clock may move back (time zones, DST, drift)
HIGH_WATER_EVERY = timedelta(minutes=10)          # how often the "latest time seen" is written to the database
CACHE_SECONDS = 60                                # the file is also re-checked at once whenever it changes on disk

FIELD_RE = re.compile(r"^REM ([A-Z][A-Z-]*):[ \t]*(.*)$")


class LicenseProblem(Exception):
    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind, self.message = kind, message


@dataclass
class Info:
    licensee: str
    license_id: str
    issued: date
    expires: date


@dataclass
class Status:
    valid: bool
    kind: str                      # ok | expired | missing | tampered | clock | locked | not_configured
    message: str
    licensee: str = ""
    expires: str = ""
    days_left: int | None = None
    lock_id: str = ""

    def public(self) -> dict:
        """What the blocked screen and the admin banner may see. No file paths, keys or internals."""
        return {"valid": self.valid, "kind": self.kind, "message": self.message, "licensee": self.licensee,
                "expires": self.expires, "days_left": self.days_left,
                "locked": self.kind == "locked", "lock_id": self.lock_id}


# ---------- reading and verifying the file ----------
def canonical(text: str) -> bytes:
    """The exact bytes that are signed: the file without its SIGNATURE line, with line endings normalised.
    CRLF/LF differences (Git on Windows), a UTF-8 BOM, trailing spaces and trailing blank lines do not matter;
    any other change does."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    lines = [ln.rstrip() for ln in text.split("\n") if not ln.startswith(SIGNATURE_PREFIX)]
    while lines and not lines[-1]:
        lines.pop()
    return ("\n".join(lines) + "\n").encode("utf-8")


def _public_key() -> Ed25519PublicKey | None:
    try:
        raw = base64.b64decode(PUBLIC_KEY_B64, validate=True)
        return Ed25519PublicKey.from_public_bytes(raw) if len(raw) == 32 else None
    except Exception:
        return None


def parse_and_verify(text: str) -> Info:
    """Return the license details only if the signature is valid. Raises LicenseProblem otherwise."""
    pub = _public_key()
    if pub is None:
        raise LicenseProblem("not_configured", "License: no license key is set up for this installation. Contact the system vendor.")
    bad = LicenseProblem("tampered", "License: the license file has been changed or is not valid. "
                                     "Restore the original file or contact the system vendor.")
    sig_lines = [ln.rstrip() for ln in text.lstrip("\ufeff").splitlines() if ln.startswith(SIGNATURE_PREFIX)]
    if len(sig_lines) != 1:
        raise bad
    try:
        signature = base64.b64decode(sig_lines[0][len(SIGNATURE_PREFIX):].strip(), validate=True)
        pub.verify(signature, canonical(text))
    except (InvalidSignature, ValueError):
        raise bad
    fields: dict[str, str] = {}
    for line in text.lstrip("\ufeff").splitlines():
        m = FIELD_RE.match(line.rstrip())
        if m and m.group(1) not in fields:
            fields[m.group(1)] = m.group(2).strip()
    try:
        if fields["PRODUCT"] != PRODUCT:
            raise bad
        info = Info(licensee=fields["LICENSEE"], license_id=fields["LICENSE-ID"],
                    issued=date.fromisoformat(fields["ISSUED"]), expires=date.fromisoformat(fields["EXPIRES"]))
    except (KeyError, ValueError):
        raise bad
    if info.expires < info.issued:
        raise bad
    return info


def candidate_paths() -> list[Path]:
    if config.LICENSE_FILE:
        return [Path(config.LICENSE_FILE)]
    here = Path(__file__).resolve()
    return [here.parents[2] / "license.bat",      # project root (backend/core/licensing.py -> project root)
            here.parents[1] / "license.bat"]      # Docker: /app/license.bat


def find_file() -> Path | None:
    return next((p for p in candidate_paths() if p.is_file()), None)


# ---------- state kept in the database (strikes, hard lock, latest time seen) ----------
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_state(db: Session) -> dict:
    row = db.get(Setting, STATE_KEY)
    base = {"strikes": 0, "problem": "", "high_water": "", "hard_locked": False, "lock_id": "", "locked_on": "",
            "license_id": "", "seen_ids": []}
    if row:
        try:
            base.update(json.loads(row.value))
        except ValueError:
            pass
    return base


def _save_state(db: Session, state: dict):
    row = db.get(Setting, STATE_KEY)
    if row:
        row.value = json.dumps(state)
    else:
        db.add(Setting(key=STATE_KEY, value=json.dumps(state)))
    db.commit()


# ---------- the check ----------
def evaluate(db: Session, now: datetime | None = None) -> Status:
    now = now or utcnow()
    state = _load_state(db)
    problem: tuple[str, str] | None = None
    info: Info | None = None

    path = find_file()
    if _public_key() is None:
        problem = ("not_configured", "License: no license key is set up for this installation. Contact the system vendor.")
    elif path is None:
        problem = ("missing", "License: the license file was not found. Restore the original file or contact the system vendor.")
    else:
        try:
            info = parse_and_verify(path.read_text(encoding="utf-8-sig"))
        except LicenseProblem as e:
            problem = (e.kind, e.message)
        except (OSError, UnicodeDecodeError):
            problem = ("tampered", "License: the license file has been changed or is not valid. "
                                   "Restore the original file or contact the system vendor.")

    if info is not None:
        if now.date() > info.expires:
            problem = ("expired", f"License: expired on {info.expires.isoformat()}. Contact the system vendor to renew.")
        else:
            seen = _parse_time(state["high_water"])
            if seen and now < seen - CLOCK_TOLERANCE:
                problem = ("clock", "License: the server clock is earlier than the last time the application ran. "
                                    "Correct the date and time, then try again.")

    kind = problem[0] if problem else "ok"
    changed = False

    # A tamper INCIDENT is counted once, when the file goes from fine to missing/altered, and only after the
    # application has had a valid license at least once (so a fresh install is not punished).
    armed = bool(state["license_id"])
    if kind in ("missing", "tampered") and armed and state["problem"] not in ("missing", "tampered"):
        state["strikes"] += 1
        audit.log(db, "license_tamper", detail=f"{kind}; strike {state['strikes']} of {MAX_STRIKES}")
        if state["strikes"] >= MAX_STRIKES and not state["hard_locked"]:
            state.update(hard_locked=True, lock_id=secrets.token_hex(4).upper(), locked_on=now.date().isoformat())
            audit.log(db, "license_hard_lock", detail=f"lock id {state['lock_id']}")
        changed = True
    if state["problem"] != kind:
        state["problem"] = kind
        changed = True

    if kind == "ok" and info is not None:
        is_new = info.license_id not in state["seen_ids"] and info.license_id != state["license_id"]
        if state["hard_locked"] and is_new and info.issued.isoformat() >= state["locked_on"]:
            # A license this installation has never seen, issued on or after the day of the lock. Only the holder of the
            # private key can sign one, so this is the vendor "regenerating" the license: it lifts the lock.
            # Putting back the original file, or any older license, does NOT (their ids are already known here).
            state.update(hard_locked=False, strikes=0, lock_id="", locked_on="")
            audit.log(db, "license_unlocked", detail="new license issued by the vendor")
            changed = True
        if info.license_id != state["license_id"]:
            if state["license_id"] and not state["hard_locked"]:
                state["strikes"] = 0                      # a genuine renewal clears the strike count
            state["license_id"] = info.license_id
            changed = True
        if is_new:
            state["seen_ids"] = (state["seen_ids"] + [info.license_id])[-50:]
            changed = True
        seen = _parse_time(state["high_water"])
        if seen is None or now - seen > HIGH_WATER_EVERY:
            state["high_water"] = now.isoformat()
            changed = True
    if changed:
        _save_state(db, state)

    days_left = (info.expires - now.date()).days if info else None
    licensee = info.licensee if info else ""
    expires = info.expires.isoformat() if info else ""
    if state["hard_locked"]:
        return Status(False, "locked", f"License: locked because the license file was deleted or changed. Contact the system "
                                       f"vendor and quote Lock ID {state['lock_id']} for an unlock code or a new license file.",
                      licensee, expires, days_left, state["lock_id"])
    if problem:
        return Status(False, kind, problem[1], licensee, expires, days_left)
    return Status(True, "ok", "License is valid.", licensee, expires, days_left)


def _parse_time(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


# ---------- cached entry point used on every request ----------
_cache: dict = {"at": 0.0, "stamp": None, "status": None}


def _stamp():
    path = find_file()
    if path is None:
        return ("none",)
    st = path.stat()
    return (str(path), st.st_mtime_ns, st.st_size)


def reset_cache():
    _cache.update(at=0.0, stamp=None, status=None)


def check(db: Session) -> Status:
    """evaluate() with a short cache. A change to the file (edit, delete, restore) is noticed on the very next request."""
    try:
        stamp = _stamp()
    except OSError:
        stamp = ("error",)
    age = time.monotonic() - _cache["at"]
    if _cache["status"] is not None and _cache["stamp"] == stamp and age < CACHE_SECONDS:
        return _cache["status"]
    status = evaluate(db)
    _cache.update(at=time.monotonic(), stamp=stamp, status=status)
    return status


# ---------- vendor unlock code ----------
def unlock_message(lock_id: str) -> bytes:
    return (UNLOCK_CONTEXT + lock_id).encode()


def apply_unlock(db: Session, token: str) -> Status:
    """Lift a hard lock with a code signed by the vendor for THIS lock id."""
    state = _load_state(db)
    if not state["hard_locked"]:
        raise ServiceError("The application is not locked.", 409)
    pub = _public_key()
    try:
        if pub is None:
            raise ValueError
        pub.verify(base64.urlsafe_b64decode(token.strip() + "=" * (-len(token.strip()) % 4)), unlock_message(state["lock_id"]))
    except (InvalidSignature, ValueError):
        raise ServiceError("That unlock code is not valid for this lock.", 400)
    state.update(hard_locked=False, strikes=0, lock_id="", locked_on="", problem="")
    _save_state(db, state)
    audit.log(db, "license_unlocked", detail="vendor unlock code accepted")
    reset_cache()
    return check(db)
