"""Admin-only endpoints. Everything the admin changes here is stored in the shared database,
so the mobile API serves the new institution name / positions / candidates immediately."""
import csv
import io

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from core import schemas, services
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
    services.delete_candidate(db, cid)
    return {"ok": True}


# --- voters ---
@router.get("/voters")
def voters(q: str = "", limit: int = Query(200, le=1000), offset: int = 0, db: Session = Depends(get_db)):
    return services.list_voters(db, q, limit, offset)


@router.post("/voters/import")
async def import_voters(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """CSV columns: matric_no, full_name, email, department, level. Returns generated PINs ONCE."""
    text = (await file.read()).decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    return services.import_voters(db, rows)


@router.post("/voters/{vid}/reset-pin")
def reset_pin(vid: int, db: Session = Depends(get_db)):
    return services.reset_pin(db, vid)


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
