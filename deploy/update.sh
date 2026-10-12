#!/usr/bin/env bash
# Get the latest version of the code from GitHub and restart. Data is kept.
#   sudo bash deploy/update.sh
set -euo pipefail
cd "$(dirname "$0")/.."
git pull --ff-only
docker compose up -d --build --remove-orphans
docker image prune -f >/dev/null
echo "Updated and running."
