import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/evoting")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-secret-change-me")
WEB_JWT_MINUTES = int(os.getenv("WEB_JWT_MINUTES", "60"))
MOBILE_JWT_MINUTES = int(os.getenv("MOBILE_JWT_MINUTES", "120"))
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
