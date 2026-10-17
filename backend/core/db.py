from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from . import config

engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from . import migrate, models  # noqa: F401  (registers tables)
    Base.metadata.create_all(engine)   # creates any missing tables (auth_sessions, audit_log, ...)
    migrate.apply(engine)              # adds new columns to tables that already existed
