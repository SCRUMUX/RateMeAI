#!/usr/bin/env bash
set -euo pipefail

# Quick update script for the RU edge server.
# Pulls latest code, rebuilds, and restarts services.
#
# Usage: sudo ./deploy/ru/update.sh

PROJECT_DIR="${PROJECT_DIR:-/opt/ratemeai}"
cd "$PROJECT_DIR"

echo "=== Pulling latest code ==="
git pull origin main

echo "=== Rebuilding frontend ==="
docker compose -f docker-compose.ru.yml --profile build-only build web

TEMP_CONTAINER=$(docker create ratemeai-web-ru:latest)
docker cp "$TEMP_CONTAINER:/usr/share/nginx/html" /tmp/web-dist
docker rm "$TEMP_CONTAINER"

docker run --rm \
    -v ratemeai_web_dist:/usr/share/nginx/html \
    -v /tmp/web-dist:/src:ro \
    alpine sh -c "rm -rf /usr/share/nginx/html/* && cp -r /src/* /usr/share/nginx/html/"
rm -rf /tmp/web-dist

echo "=== Rebuilding and restarting backend ==="
docker compose -f docker-compose.ru.yml up -d --build app

echo "=== Reloading nginx ==="
docker compose -f docker-compose.ru.yml exec nginx nginx -s reload

echo "=== Done ==="
docker compose -f docker-compose.ru.yml ps
echo ""
echo "Health: curl -s https://ru.ailookstudio.ru/health"
