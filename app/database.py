from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

_is_sqlite = settings.database_url.startswith("sqlite")
_is_postgres = settings.database_url.startswith("postgresql")

# ─── Engine Configuration ─────────────────────────────────────────────────────
# pool_pre_ping: verify connections before use (critical for long-running
#   processes and serverless/Docker restarts where the DB may have restarted).
# pool_size / max_overflow: keep a small warm pool; fine for a personal hub.

connect_args = {"check_same_thread": False} if _is_sqlite else {}

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=True,
    **({} if _is_sqlite else {
        "pool_size": 5,
        "max_overflow": 10,
        "pool_recycle": 1800,   # Recycle connections after 30 min (prevents stale connections)
    }),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ─── SQLite-only pragmas ──────────────────────────────────────────────────────
# WAL mode + performance pragmas.  Only applied for SQLite (local dev fallback).
if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA cache_size=-32000")  # 32 MB page cache
        cursor.close()


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
