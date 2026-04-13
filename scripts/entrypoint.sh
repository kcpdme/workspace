#!/bin/bash
# entrypoint.sh — Runs before the app starts inside Docker.
# 1. Waits for PostgreSQL to be reachable.
# 2. Runs Alembic migrations (safe to run on every restart — idempotent).
# 3. Starts the FastAPI app.

set -e

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║        Personal Automation Hub           ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Wait for PostgreSQL ──────────────────────────────────────────────────────
# Only needed when DATABASE_URL points to postgres (not SQLite).
if echo "${DATABASE_URL:-}" | grep -q "postgresql"; then
    echo "[startup] Waiting for PostgreSQL..."
    python - <<'EOF'
import os, sys, time
try:
    import sqlalchemy
except ImportError:
    sys.exit(0)

url = os.environ.get("DATABASE_URL", "")
if not url.startswith("postgresql"):
    sys.exit(0)

for attempt in range(1, 31):
    try:
        engine = sqlalchemy.create_engine(url, pool_pre_ping=True)
        with engine.connect():
            pass
        print(f"[startup] PostgreSQL ready after {attempt} attempt(s).")
        sys.exit(0)
    except Exception as e:
        print(f"[startup] Not ready yet ({attempt}/30): {e}")
        time.sleep(2)

print("[startup] ERROR: PostgreSQL did not become ready in time.", file=sys.stderr)
sys.exit(1)
EOF
fi

# ── Run Alembic migrations ───────────────────────────────────────────────────
echo "[startup] Running database migrations..."
python - <<'EOF'
from sqlalchemy import create_engine, inspect
from app.config import settings

engine = create_engine(settings.database_url)
with engine.connect() as conn:
    inspector = inspect(conn)
    has_alembic_version = inspector.has_table("alembic_version")
    user_tables = [t for t in inspector.get_table_names() if t != "alembic_version"]

if not has_alembic_version:
    if user_tables:
        print("[startup] Existing schema detected without alembic_version; stamping head.")
    else:
        print("[startup] Empty database detected; creating schema and stamping head.")
        from app.database import init_db
        init_db()
EOF

if python - <<'EOF'
from sqlalchemy import create_engine, inspect
from app.config import settings

engine = create_engine(settings.database_url)
with engine.connect() as conn:
    inspector = inspect(conn)
    has_alembic_version = inspector.has_table("alembic_version")
    user_tables = [t for t in inspector.get_table_names() if t != "alembic_version"]

if has_alembic_version:
    raise SystemExit(0)
raise SystemExit(1 if user_tables else 2)
EOF
then
    alembic upgrade head
else
    state=$?
    if [ "$state" -eq 1 ] || [ "$state" -eq 2 ]; then
        alembic stamp head
    else
        exit "$state"
    fi
fi
echo "[startup] Migrations complete."
echo ""

# ── Start the app ────────────────────────────────────────────────────────────
echo "[startup] Starting AutoHub on 0.0.0.0:8000"
exec python -m uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 1 \
    --log-level info
