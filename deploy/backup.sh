#!/usr/bin/env bash
# Save a copy of the database into ./backups (keeps the last 14).
#   sudo bash deploy/backup.sh
# Daily at 3:00, add to root's crontab (sudo crontab -e):
#   0 3 * * * cd /root/travel-ai-agency && bash deploy/backup.sh >/dev/null 2>&1
# Restore a backup (replaces the current data!):
#   gunzip -c backups/FILE.sql.gz | docker compose exec -T db psql -U travel -d travel_ai
set -euo pipefail
cd "$(dirname "$0")/.."
value() { grep -E "^$1=" .env | tail -n 1 | cut -d= -f2- || true; }
user=$(value POSTGRES_USER); db=$(value POSTGRES_DB)
mkdir -p backups
file="backups/${db:-travel_ai}-$(date +%Y-%m-%d-%H%M).sql.gz"
docker compose exec -T db pg_dump -U "${user:-travel}" --clean --if-exists "${db:-travel_ai}" | gzip > "$file"
ls -1t backups/*.sql.gz | tail -n +15 | xargs -r rm --
echo "Saved $file"
