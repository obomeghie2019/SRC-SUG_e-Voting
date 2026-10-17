"""Lightweight, idempotent schema upgrade for databases created before the OTP/forensics release.

SQLAlchemy's create_all() creates missing TABLES but never adds COLUMNS to existing tables, so this
adds the new columns (voters.phone, forensic columns on vote_receipts) when they are missing.
Safe to run on every start-up; works on MySQL, PostgreSQL and SQLite.
"""
import logging

from sqlalchemy import Column, Float, String, inspect, text

log = logging.getLogger("evoting.migrate")

# (table, column) -> what to add
NEW_COLUMNS = [
    ("voters", Column("phone", String(30), nullable=False, server_default="")),
    ("vote_receipts", Column("session_id", String(36), nullable=True)),
    ("vote_receipts", Column("ip", String(64), nullable=True)),
    ("vote_receipts", Column("latitude", Float, nullable=True)),
    ("vote_receipts", Column("longitude", Float, nullable=True)),
    ("vote_receipts", Column("accuracy_m", Float, nullable=True)),
    ("vote_receipts", Column("user_agent", String(300), nullable=True)),
    ("vote_receipts", Column("device_id", String(100), nullable=True)),
]


def _ddl(engine, table: str, col: Column) -> str:
    coltype = col.type.compile(dialect=engine.dialect)
    sql = f"ALTER TABLE {table} ADD COLUMN {col.name} {coltype}"
    if col.server_default is not None:
        sql += f" NOT NULL DEFAULT '{col.server_default.arg}'"
    return sql


def apply(engine) -> list[str]:
    """Add any missing columns. Returns the list of 'table.column' names that were added."""
    added = []
    insp = inspect(engine)
    for table, col in NEW_COLUMNS:
        if not insp.has_table(table):
            continue  # create_all() will build it with every column
        existing = {c["name"] for c in insp.get_columns(table)}
        if col.name in existing:
            continue
        try:
            with engine.begin() as conn:
                conn.execute(text(_ddl(engine, table, col)))
            added.append(f"{table}.{col.name}")
        except Exception as exc:  # another process may have added it first
            log.warning("Could not add %s.%s: %s", table, col.name, exc)
    if added:
        log.warning("Schema upgraded, added columns: %s", ", ".join(added))
    return added
