"""Voter routes shared by the web API and the mobile API.
Each API mounts this router under its own prefix with its own JWT audience, so the two apps
stay separate (a web token is rejected by the mobile API and the other way round)."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from . import audit, otp, schemas, services
from .audit import ClientInfo
from .db import get_db
from .security import make_token, require


def build_router(audience: str, client: str, token_minutes: int) -> APIRouter:
    router = APIRouter()
    voter_only = require(audience, "voter")

    def verified(claims: dict = Depends(voter_only), db: Session = Depends(get_db)) -> tuple[dict, object]:
        return claims, otp.assert_verified(db, claims, client)

    @router.post("/auth/lookup")
    def lookup(body: schemas.LookupIn, request: Request, db: Session = Depends(get_db)):
        """Step 1: matric number + location. Returns a session id and the masked contacts on record."""
        return otp.start_session(db, body.matric_no, client, ClientInfo.from_request(request, body), body.device_id)

    @router.post("/auth/otp/send")
    def send(body: schemas.SendOtpIn, request: Request, db: Session = Depends(get_db)):
        """Step 2: send the code by email or SMS to the contact stored for this voter."""
        return otp.send_code(db, body.session_id, body.channel, client, ClientInfo.from_request(request))

    @router.post("/auth/otp/verify")
    def verify(body: schemas.VerifyOtpIn, request: Request, db: Session = Depends(get_db)):
        """Step 3: check the code against THIS session; on success return the voting token."""
        voter, session = otp.verify_code(db, body.session_id, body.otp, client, ClientInfo.from_request(request, body))
        token = make_token(voter.id, "voter", audience, token_minutes, extra={"sid": session.id})
        return {"token": token, "voter": {"full_name": voter.full_name, "matric_no": voter.matric_no}}

    @router.get("/ballot")
    def ballot(ctx: tuple = Depends(verified), db: Session = Depends(get_db)):
        return services.get_ballot(db, int(ctx[0]["sub"]))

    @router.post("/vote")
    def vote(body: schemas.VoteIn, request: Request, ctx: tuple = Depends(verified), db: Session = Depends(get_db)):
        claims, session = ctx
        info = ClientInfo.from_request(request, body)
        code = services.cast_vote(db, int(claims["sub"]), body.selections, client, info, session)
        audit.log(db, "vote_cast", voter_id=int(claims["sub"]), session_id=session.id, info=info, detail=client)
        return {"receipt_code": code}

    return router
