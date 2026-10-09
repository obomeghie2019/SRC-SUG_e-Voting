"""WEB API  ->  /api/web/*   (React voter site + admin dashboard)
Run:  uvicorn api_web.main:app --port 8001 --reload"""
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from core import config, schemas, services
from core.db import get_db, init_db
from core.security import WEB, make_token, require
from . import admin

app = FastAPI(title="SUG/SRC e-Voting: Web API")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(services.ServiceError)
async def service_error(_: Request, exc: services.ServiceError):
    return JSONResponse({"detail": exc.message}, status_code=exc.status)


@app.on_event("startup")
def startup():
    init_db()


voter_only = require(WEB, "voter")


@app.get("/api/web/config")
def public_config(db: Session = Depends(get_db)):
    return services.public_config(db)


@app.post("/api/web/auth/login")
def voter_login(body: schemas.VoterLogin, db: Session = Depends(get_db)):
    v = services.authenticate_voter(db, body.matric_no, body.password)
    if not v:
        raise HTTPException(401, "Invalid matric number or PIN")
    return {"token": make_token(v.id, "voter", WEB, config.WEB_JWT_MINUTES),
            "voter": {"full_name": v.full_name, "matric_no": v.matric_no}}


@app.post("/api/web/auth/admin/login")
def admin_login(body: schemas.AdminLogin, db: Session = Depends(get_db)):
    a = services.authenticate_admin(db, body.username, body.password)
    if not a:
        raise HTTPException(401, "Invalid username or password")
    return {"token": make_token(a.id, "admin", WEB, config.WEB_JWT_MINUTES), "admin": {"full_name": a.full_name}}


@app.get("/api/web/ballot")
def ballot(claims: dict = Depends(voter_only), db: Session = Depends(get_db)):
    return services.get_ballot(db, int(claims["sub"]))


@app.post("/api/web/vote")
def vote(body: schemas.VoteIn, claims: dict = Depends(voter_only), db: Session = Depends(get_db)):
    code = services.cast_vote(db, int(claims["sub"]), body.selections, channel="web")
    return {"receipt_code": code}


app.include_router(admin.router, prefix="/api/web/admin")
