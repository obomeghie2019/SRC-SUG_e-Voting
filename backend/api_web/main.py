"""WEB API  ->  /api/web/*   (React voter site + admin dashboard)
Run:  uvicorn api_web.main:app --port 8001 --reload"""
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from core import config, licensing_api, schemas, services
from core.db import get_db, init_db
from core.security import WEB, make_token
from core.voter_router import build_router
from . import admin

app = FastAPI(title="SUG/SRC e-Voting: Web API")
os.makedirs(config.UPLOAD_DIR, exist_ok=True)
# Logo and candidate photos uploaded by the admin (stored as '/uploads/<name>' in the database)
app.mount("/api/web/uploads", StaticFiles(directory=config.UPLOAD_DIR), name="uploads")
# License gate first, then CORS: CORS then wraps the gate, so a blocked response still carries CORS headers
licensing_api.install(app, "/api/web")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(services.ServiceError)
async def service_error(_: Request, exc: services.ServiceError):
    return JSONResponse({"detail": exc.message}, status_code=exc.status)


@app.on_event("startup")
def startup():
    init_db()
    licensing_api.log_startup()


@app.get("/api/web/config")
def public_config(db: Session = Depends(get_db)):
    return services.public_config(db)


@app.post("/api/web/auth/admin/login")
def admin_login(body: schemas.AdminLogin, db: Session = Depends(get_db)):
    a = services.authenticate_admin(db, body.username, body.password)
    if not a:
        raise HTTPException(401, "Invalid username or password")
    return {"token": make_token(a.id, "admin", WEB, config.WEB_JWT_MINUTES), "admin": {"full_name": a.full_name}}


# voter sign-in (location -> matric -> email/SMS code), ballot and vote
app.include_router(build_router(WEB, "web", config.VOTE_TOKEN_MINUTES), prefix="/api/web")
app.include_router(admin.router, prefix="/api/web/admin")
