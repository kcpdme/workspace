#!/bin/bash
# backup_pg.sh — Daily PostgreSQL backup via pg_dump inside Docker
# 
# Setup (on server): add to crontab:
#   0 3 * * * /path/to/workspace/scripts/backup_pg.sh >> /var/log/hub_backup.log 2>&1
#
# Backups are kept for 14 days then auto-deleted.

set -euo pipefail

BACKUP_DIR="/opt/hub_backups"
CONTAINER="automation-hub-db"
DB_NAME="automationhub"
DB_USER="hubuser"
DATE=$(date +%Y%m%d_%H%M%S)
FILE="${BACKUP_DIR}/hub_${DATE}.sql.gz"

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup → $FILE"
docker exec "$CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$FILE"
echo "[$(date)] Backup complete: $(du -sh "$FILE" | cut -f1)"

# Delete backups older than 14 days
find "$BACKUP_DIR" -name "hub_*.sql.gz" -mtime +14 -delete
echo "[$(date)] Old backups pruned. Current backups:"
ls -lh "$BACKUP_DIR"
