import os
from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/evoting")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me")
WEB_JWT_MINUTES = int(os.getenv("WEB_JWT_MINUTES", "60"))
MOBILE_JWT_MINUTES = int(os.getenv("MOBILE_JWT_MINUTES", "120"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]

# ---- Voter sign-in: location + OTP ----
LOCATION_REQUIRED = _bool("LOCATION_REQUIRED", True)
# Optional campus geofence. Leave GEOFENCE_RADIUS_M at 0 to switch it off.
GEOFENCE_LAT = _float("GEOFENCE_LAT", 0.0)
GEOFENCE_LNG = _float("GEOFENCE_LNG", 0.0)
GEOFENCE_RADIUS_M = _float("GEOFENCE_RADIUS_M", 0.0)

OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", "5"))          # how long a code stays valid
OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))        # wrong guesses before the session locks
OTP_SEND_LIMIT = int(os.getenv("OTP_SEND_LIMIT", "3"))            # codes per voter per window
OTP_IP_SEND_LIMIT = int(os.getenv("OTP_IP_SEND_LIMIT", "15"))     # codes per IP per window
OTP_SEND_WINDOW_MINUTES = int(os.getenv("OTP_SEND_WINDOW_MINUTES", "10"))
LOOKUP_FAIL_LIMIT = int(os.getenv("LOOKUP_FAIL_LIMIT", "10"))     # unknown matric numbers per IP per window
SESSION_MINUTES = int(os.getenv("SESSION_MINUTES", "15"))         # sign-in session lifetime
VOTE_TOKEN_MINUTES = int(os.getenv("VOTE_TOKEN_MINUTES", "30"))   # voting token lifetime after OTP success

# DEV ONLY: print codes to the API console instead of sending them. Never enable in production.
OTP_DEV_MODE = _bool("OTP_DEV_MODE", False)

# Trust X-Forwarded-For for the voter IP (only when running behind your own nginx/proxy)
TRUST_PROXY = _bool("TRUST_PROXY", False)

# ---- Email (SMTP) ----
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER
SMTP_STARTTLS = _bool("SMTP_STARTTLS", True)                      # port 465 uses implicit SSL automatically

# ---- SMS ----
SMS_PROVIDER = os.getenv("SMS_PROVIDER", "").strip().lower()      # termii | africastalking | twilio | (empty = off)
SMS_API_KEY = os.getenv("SMS_API_KEY", "")                        # Twilio: auth token
SMS_USERNAME = os.getenv("SMS_USERNAME", "")                      # Africa's Talking username / Twilio account SID
SMS_SENDER_ID = os.getenv("SMS_SENDER_ID", "")                    # approved sender name, or Twilio phone number
DEFAULT_COUNTRY_CODE = os.getenv("DEFAULT_COUNTRY_CODE", "234")   # used to normalise numbers like 0801...

# ---- Uploaded images (school logo, candidate photos) ----
UPLOAD_DIR = os.getenv("UPLOAD_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "2"))
