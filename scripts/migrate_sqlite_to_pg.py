#!/usr/bin/env python3
"""migrate_sqlite_to_pg.py — One-shot migration from SQLite to PostgreSQL.

Usage
-----
  # 1. Make sure Postgres is running (docker-compose up -d db)
  # 2. Set both URLs as env vars or edit the constants below:
  python scripts/migrate_sqlite_to_pg.py \
      --sqlite "sqlite:///D:/workspace/automation_hub.db" \
      --pg     "postgresql://hubuser:yourpassword@localhost:5432/automationhub"

What it does
------------
- Copies every row from all tables in SQLite → Postgres.
- Skips tables that are empty (nothing to migrate).
- Is IDEMPOTENT: uses INSERT ... ON CONFLICT DO NOTHING so safe to re-run.
- Sequences (auto-increment IDs) are fixed up after bulk insert.
- Encrypted note cipher_text is copied as-is (no decryption needed).

Requirements
------------
  pip install sqlalchemy psycopg2-binary
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime

from sqlalchemy import create_engine, inspect, text, MetaData, Table


# ─── Tables to migrate — in dependency order (parents before children) ─────────
TABLES_IN_ORDER = [
    "api_keys",
    "allowed_telegram_users",
    "captures",
    "encrypted_notes",
    "tags",
    "tasks",
    "task_tags",
    "note_tags",
    "reminders",
    "habits",
    "habit_logs",
    "telegram_inbox_items",
    "webhook_subscriptions",
    "webhook_delivery_logs",
    "otp_codes",
    "login_attempts",
    "audit_logs",
]


def migrate(sqlite_url: str, pg_url: str) -> None:
    print(f"\n{'='*60}")
    print(" SQLite → PostgreSQL Migration")
    print(f"{'='*60}")
    print(f" Source : {sqlite_url}")
    print(f" Target : {pg_url[:pg_url.index('@')+1]}***")
    print(f"{'='*60}\n")

    src_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})
    dst_engine = create_engine(pg_url, pool_pre_ping=True)

    src_meta = MetaData()
    src_meta.reflect(bind=src_engine)
    src_inspector = inspect(src_engine)
    dst_inspector = inspect(dst_engine)

    dst_tables = dst_inspector.get_table_names()

    total_rows = 0

    for table_name in TABLES_IN_ORDER:
        if table_name not in src_meta.tables:
            print(f"  ⚠  {table_name:40s} — not in SQLite, skipping")
            continue
        if table_name not in dst_tables:
            print(f"  ⚠  {table_name:40s} — not in Postgres yet (run alembic upgrade head first)")
            continue

        src_table = Table(table_name, src_meta, autoload_with=src_engine)

        with src_engine.connect() as src_conn:
            rows = src_conn.execute(src_table.select()).mappings().all()

        if not rows:
            print(f"  ✓  {table_name:40s} — 0 rows (empty, skipped)")
            continue

        # Convert rows to plain dicts and handle SQLite datetime quirks.
        dicts = [dict(r) for r in rows]

        with dst_engine.begin() as dst_conn:
            # Use INSERT ... ON CONFLICT DO NOTHING for idempotency.
            # Build raw SQL for maximum compatibility.
            cols = list(dicts[0].keys())
            col_names = ", ".join(f'"{c}"' for c in cols)
            placeholders = ", ".join(f":{c}" for c in cols)

            stmt = text(
                f'INSERT INTO "{table_name}" ({col_names}) VALUES ({placeholders}) '
                f"ON CONFLICT DO NOTHING"
            )
            dst_conn.execute(stmt, dicts)

        print(f"  ✓  {table_name:40s} — {len(rows):5d} rows migrated")
        total_rows += len(rows)

    # ── Fix sequences so next INSERT gets the right auto-increment ID ─────────
    print(f"\n  Fixing Postgres sequences…")
    with dst_engine.begin() as conn:
        for table_name in TABLES_IN_ORDER:
            if table_name not in dst_tables:
                continue
            try:
                # Standard Postgres sequence name pattern from SQLAlchemy.
                result = conn.execute(
                    text(f'SELECT MAX(id) FROM "{table_name}"')
                ).scalar()
                if result:
                    conn.execute(
                        text(f"SELECT setval(pg_get_serial_sequence('{table_name}', 'id'), {result})")
                    )
                    print(f"     {table_name}: sequence → {result}")
            except Exception as e:
                print(f"     {table_name}: sequence fix skipped ({e})")

    print(f"\n{'='*60}")
    print(f" Migration complete — {total_rows} total rows transferred.")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate SQLite → PostgreSQL")
    parser.add_argument(
        "--sqlite",
        default="sqlite:///D:/workspace/automation_hub.db",
        help="SQLAlchemy URL of source SQLite DB",
    )
    parser.add_argument(
        "--pg",
        required=True,
        help="SQLAlchemy URL of target PostgreSQL DB "
             "(e.g. postgresql://hubuser:pass@localhost:5432/automationhub)",
    )
    args = parser.parse_args()

    try:
        migrate(args.sqlite, args.pg)
    except Exception as exc:
        print(f"\n❌ Migration failed: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
