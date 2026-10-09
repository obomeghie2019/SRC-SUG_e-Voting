import datetime as dt
import bcrypt
import jwt
from fastapi import Header, HTTPException
from . import config

WEB, MOBILE = "web", "mobile"  # JWT audiences: a mobile token is rejected by the web API and vice versa


def hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()


def verify_pw(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def make_token(sub: int, role: str, aud: str, minutes: int) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    payload = {"sub": str(sub), "role": role, "aud": aud, "iat": now, "exp": now + dt.timedelta(minutes=minutes)}
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def require(aud: str, role: str):
    """FastAPI dependency: validates Bearer JWT for a given audience + role."""
    def dep(authorization: str = Header(default="")) -> dict:
        if not authorization.startswith("Bearer "):
            raise HTTPException(401, "Missing token")
        try:
            claims = jwt.decode(authorization[7:], config.JWT_SECRET, algorithms=["HS256"], audience=aud)
        except jwt.PyJWTError:
            raise HTTPException(401, "Invalid or expired token")
        if claims.get("role") != role:
            raise HTTPException(403, "Forbidden")
        return claims
    return dep
