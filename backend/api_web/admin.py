"""Admin-only endpoints. Everything the admin changes here is stored in the shared database,
so the mobile API serves the new institution name / positions / candidates immediately."""
import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from core import audit, delivery, notify, schemas, services, uploads
from core.db import get_db
from core.security import WEB, require

router = APIRouter(dependencies=[Depends(require(WEB, "admin"))])


# --- system settings (institution name, title, logo, colour) ---
@router.get("/settings")
def get_settings(db: Session = Depends(get_db)):
    return services.get_settings(db)


@router.put("/settings")
def put_settings(body: dict[str, str], db: Session = Depends(get_db)):
    return services.update_settings(db, body)


@router.post("/settings/logo")
async def upload_logo(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload the school logo (PNG/JPG/GIF/WebP, max MAX_UPLOAD_MB). Web and mobile show it immediately."""
    url = uploads.save_image(await uploads.read_limited(file))
    old = services.get_settings(db)["logo_url"]
    services.update_settings(db, {"logo_url": url})
    uploads.delete_file(old)
    return {"logo_url": url}


@router.delete("/settings/logo")
def remove_logo(db: Session = Depends(get_db)):
    old = services.get_settings(db)["logo_url"]
    services.update_settings(db, {"logo_url": ""})
    uploads.delete_file(old)
    return {"logo_url": ""}


@router.post("/election/status")
def election_status(body: schemas.StatusIn, db: Session = Depends(get_db)):
    return services.set_status(db, body.status)


@router.post("/election/reset")
def election_reset(body: schemas.ResetIn, db: Session = Depends(get_db)):
    if body.confirm != "RESET":
        raise HTTPException(400, 'Type "RESET" to confirm')
    services.reset_election(db)
    return {"ok": True}


# --- positions & candidates ---
@router.get("/positions")
def positions(db: Session = Depends(get_db)):
    return services.admin_positions(db)


@router.post("/positions")
def add_position(body: schemas.PositionIn, db: Session = Depends(get_db)):
    p = services.create_position(db, body.title, body.display_order)
    return {"id": p.id}


@router.put("/positions/{pid}")
def edit_position(pid: int, body: schemas.PositionIn, db: Session = Depends(get_db)):
    services.update_position(db, pid, body.title, body.display_order)
    return {"ok": True}


@router.delete("/positions/{pid}")
def remove_position(pid: int, db: Session = Depends(get_db)):
    services.delete_position(db, pid)
    return {"ok": True}


@router.post("/candidates/import")
async def import_candidates(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """CSV columns: position, full_name, department, level, manifesto, photo_url (draft only)."""
    text = (await file.read()).decode("utf-8-sig")
    return services.import_candidates(db, list(csv.DictReader(io.StringIO(text))))


@router.post("/candidates/{cid}/photo")
async def candidate_photo(cid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a candidate photo (PNG/JPG/GIF/WebP, max MAX_UPLOAD_MB). Draft only."""
    cand = services.candidate_for_photo(db, cid)
    url = uploads.save_image(await uploads.read_limited(file))
    old, cand.photo_url = cand.photo_url, url
    db.commit()
    uploads.delete_file(old)
    return {"photo_url": url}


@router.delete("/candidates/{cid}/photo")
def candidate_photo_remove(cid: int, db: Session = Depends(get_db)):
    cand = services.candidate_for_photo(db, cid)
    old, cand.photo_url = cand.photo_url, ""
    db.commit()
    uploads.delete_file(old)
    return {"photo_url": ""}


@router.post("/candidates")
def add_candidate(body: schemas.CandidateIn, db: Session = Depends(get_db)):
    c = services.create_candidate(db, body.model_dump())
    return {"id": c.id}


@router.put("/candidates/{cid}")
def edit_candidate(cid: int, body: schemas.CandidateIn, db: Session = Depends(get_db)):
    services.update_candidate(db, cid, body.model_dump())
    return {"ok": True}


@router.delete("/candidates/{cid}")
def remove_candidate(cid: int, db: Session = Depends(get_db)):
    old_photo = services.candidate_photo_of(db, cid)
    services.delete_candidate(db, cid)
    uploads.delete_file(old_photo)
    return {"ok": True}


# --- voters ---
@router.get("/voters")
def voters(q: str = "", limit: int = Query(200, le=1000), offset: int = 0, db: Session = Depends(get_db)):
    return services.list_voters(db, q, limit, offset)


@router.post("/voters/import")
async def import_voters(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """CSV columns: matric_no, full_name, email, phone, department, level.
    Existing matric numbers get their email/phone updated. Voters sign in with an OTP, so no PINs exist."""
    text = (await file.read()).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    return services.import_voters(db, rows)


@router.put("/voters/{vid}/contact")
def voter_contact(vid: int, body: schemas.ContactIn, db: Session = Depends(get_db)):
    return services.update_voter_contact(db, vid, body.email, body.phone)


@router.post("/voters/{vid}/active")
def voter_active(vid: int, active: bool, db: Session = Depends(get_db)):
    services.set_voter_active(db, vid, active)
    return {"ok": True}


# --- live monitoring & analytics ---
@router.get("/live")
def live(db: Session = Depends(get_db)):
    return services.live(db)


@router.get("/analytics")
def analytics(db: Session = Depends(get_db)):
    return services.analytics(db)


# --- forensic report (who voted, when, from where; never WHAT they voted for) ---
@router.get("/reports/forensic")
def forensic(q: str = "", claims: dict = Depends(require(WEB, "admin")), db: Session = Depends(get_db)):
    audit.log(db, "forensic_report_viewed", detail=f"admin id {claims['sub']}")
    return audit.forensic_report(db, q)


@router.get("/reports/events")
def events(event: str = "", limit: int = Query(200, le=2000), offset: int = 0, db: Session = Depends(get_db)):
    """Security events: failed lookups, OTP sends and failures, votes cast, report views."""
    return audit.events(db, limit, offset, event)


# --- email (SMTP), SMS provider and code rules, managed from the dashboard ---
@router.get("/delivery")
def get_delivery(db: Session = Depends(get_db)):
    return delivery.view(db)


@router.put("/delivery")
def put_delivery(body: schemas.DeliveryIn, claims: dict = Depends(require(WEB, "admin")), db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True, exclude={"clear_secrets"})
    changed = delivery.save(db, {k: v for k, v in data.items() if v is not None}, body.clear_secrets)
    audit.log(db, "delivery_settings_changed", detail=f"admin id {claims['sub']}: {', '.join(changed)}")  # names only, never values
    return delivery.view(db)


@router.post("/delivery/test-email")
def test_email(body: schemas.TestSendIn, claims: dict = Depends(require(WEB, "admin")), db: Session = Depends(get_db)):
    msg = notify.send_test(delivery.load(db), "email", body.to.strip(), services.get_settings(db)["institution_name"])
    audit.log(db, "delivery_test", detail=f"admin id {claims['sub']}: email")
    return {"message": msg}


@router.post("/delivery/test-sms")
def test_sms(body: schemas.TestSendIn, claims: dict = Depends(require(WEB, "admin")), db: Session = Depends(get_db)):
    msg = notify.send_test(delivery.load(db), "sms", body.to.strip(), services.get_settings(db)["institution_name"])
    audit.log(db, "delivery_test", detail=f"admin id {claims['sub']}: sms")
    return {"message": msg}
