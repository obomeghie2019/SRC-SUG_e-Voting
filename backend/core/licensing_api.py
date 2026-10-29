"""Hooks the license check into an API: every request is refused (403) while the license is not valid,
except the two small endpoints the blocked screen needs."""
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from . import audit, licensing
from .audit import client_ip
from .db import SessionLocal, get_db
from .errors import ServiceError

log = logging.getLogger("evoting.license")
UNLOCK_FAIL_LIMIT = 10


class UnlockIn(BaseModel):
    token: str = Field(min_length=20, max_length=200)


def _check_once():
    db = SessionLocal()
    try:
        return licensing.check(db)
    finally:
        db.close()


def build_router() -> APIRouter:
    router = APIRouter()

    @router.get("/license")
    def info(db: Session = Depends(get_db)):
        return licensing.check(db).public()

    @router.post("/license/unlock")
    def unlock(body: UnlockIn, request: Request, db: Session = Depends(get_db)):
        ip = client_ip(request)
        since = audit.utcnow() - timedelta(minutes=10)
        if ip and audit.count(db, "license_unlock_failed", since, ip=ip) >= UNLOCK_FAIL_LIMIT:
            raise ServiceError("Too many attempts. Try again later.", 429)
        try:
            return licensing.apply_unlock(db, body.token).public()
        except ServiceError as e:
            if e.status == 400:
                audit.log(db, "license_unlock_failed", info=audit.ClientInfo(ip=ip))
            raise

    return router


def install(app: FastAPI, prefix: str):
    """Call BEFORE adding the CORS middleware, so CORS headers are also added to the 403 response."""
    exempt = {f"{prefix}/license", f"{prefix}/license/unlock"}

    @app.middleware("http")
    async def license_gate(request: Request, call_next):
        if request.method == "OPTIONS" or request.url.path in exempt:
            return await call_next(request)
        try:
            status = await run_in_threadpool(_check_once)
        except Exception:  # fail closed: if the check cannot run, nothing runs
            log.exception("License check could not run")
            return JSONResponse({"detail": "License: the license check could not be completed. Try again shortly."}, status_code=503)
        if not status.valid:
            return JSONResponse({"detail": status.message, "license": status.public()}, status_code=403)
        return await call_next(request)

    app.include_router(build_router(), prefix=prefix)


def log_startup():
    """Prints the license state in the server console at start-up (call after init_db())."""
    try:
        status = _check_once()
    except Exception as exc:
        print(f"[LICENSE] could not be checked: {exc}", flush=True)
        return
    if status.valid:
        print(f"[LICENSE] valid for {status.licensee}, expires {status.expires} ({status.days_left} days left)", flush=True)
    else:
        print(f"[LICENSE] BLOCKED ({status.kind}): {status.message}", flush=True)
