"""MOBILE API  ->  /api/mobile/*   (Flutter app)
Separate app, separate folder, separate JWT audience. Shares only core/ (database + rules).
Run:  uvicorn api_mobile.main:app --port 8002 --reload"""
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core import config, schemas, services
from core.db import get_db, init_db
from core.models import Voter
from core.security import MOBILE, make_token, require

app = FastAPI(title="SUG/SRC e-Voting: Mobile API")
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


@app.post("/api/mobile/auth/login")
def login(body: schemas.MobileVoterLogin, db: Session = Depends(get_db)):
    v = services.authenticate_voter(db, body.matric_no, body.password)
    if not v:
        raise HTTPException(401, "Invalid matric number or PIN")
    return {"token": make_token(v.id, "voter", MOBILE, config.MOBILE_JWT_MINUTES),
            "full_name": v.full_name, "matric_no": v.matric_no}


@app.get("/api/mobile/me")
def me(claims: dict = Depends(voter_only), db: Session = Depends(get_db)):
    v = db.get(Voter, int(claims["sub"]))
    return {"full_name": v.full_name, "matric_no": v.matric_no, "department": v.department, "level": v.level}


@app.get("/api/mobile/ballot")
def ballot(claims: dict = Depends(voter_only), db: Session = Depends(get_db)):
    return services.get_ballot(db, int(claims["sub"]))


@app.post("/api/mobile/vote")
def vote(body: schemas.VoteIn, claims: dict = Depends(voter_only), db: Session = Depends(get_db)):
    return {"receipt_code": services.cast_vote(db, int(claims["sub"]), body.selections, channel="mobile")}


@app.get("/api/mobile/results")
def results(_: dict = Depends(voter_only), db: Session = Depends(get_db)):
    s = services.get_settings(db)
    if s["election_status"] != "closed" or s["show_results_to_voters"] != "true":
        raise HTTPException(403, "Results are not published")
    return services.results(db)
