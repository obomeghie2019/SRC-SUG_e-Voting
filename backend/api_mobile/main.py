"""MOBILE API  ->  /api/mobile/*   (Flutter app)
Separate app, separate folder, separate JWT audience. Shares only core/ (database + rules).
Run:  uvicorn api_mobile.main:app --port 8002 --reload"""
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from core import config, services
from core.db import get_db, init_db
from core.models import Voter
from core.security import MOBILE, require
from core.voter_router import build_router

app = FastAPI(title="SUG/SRC e-Voting: Mobile API")
os.makedirs(config.UPLOAD_DIR, exist_ok=True)
# Logo and candidate photos uploaded by the admin (stored as '/uploads/<name>' in the database)
app.mount("/api/mobile/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])  # native apps don't need CORS


@app.exception_handler(services.ServiceError)
async def service_error(_: Request, exc: services.ServiceError):
    return JSONResponse({"detail": exc.message}, status_code=exc.status)


@app.on_event("startup")
def startup():
    init_db()


voter_only = require(MOBILE, "voter")


@app.get("/api/mobile/config")
def public_config(db: Session = Depends(get_db)):
    return services.public_config(db)


# voter sign-in (location -> matric -> email/SMS code), ballot and vote
app.include_router(build_router(MOBILE, "mobile", config.VOTE_TOKEN_MINUTES), prefix="/api/mobile")


@app.get("/api/mobile/me")
def me(claims: dict = Depends(voter_only), db: Session = Depends(get_db)):
    v = db.get(Voter, int(claims["sub"]))
    return {"full_name": v.full_name, "matric_no": v.matric_no, "department": v.department, "level": v.level}


@app.get("/api/mobile/results")
def results(_: dict = Depends(voter_only), db: Session = Depends(get_db)):
    s = services.get_settings(db)
    if s["election_status"] != "closed" or s["show_results_to_voters"] != "true":
        raise HTTPException(403, "Results are not published")
    return services.results(db)
