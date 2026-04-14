#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────────────────────────────────────────────
# RU edge server deployment script.
# Single source of truth — called by CI and manual deploys alike.
#
# Usage:
#   sudo ./deploy/ru/update.sh              # manual
#   DEPLOY_GIT_SHA=abc123 ./deploy/ru/update.sh  # CI passes SHA
# ────────────────────────────────────────────────────────────────

PROJECT_DIR="${PROJECT_DIR:-/opt/ratemeai}"
COMPOSE_FILE="docker-compose.ru.yml"
DOMAIN="https://ru.ailookstudio.ru"

cd "$PROJECT_DIR"

SHORT_SHA="${DEPLOY_GIT_SHA:-$(git rev-parse --short=12 HEAD)}"
export DEPLOY_GIT_SHA="$SHORT_SHA"

echo "=== RU Deploy: SHA=$SHORT_SHA ==="

# ── 1. Pull latest code ─────────────────────────────────────────
echo "--- git pull ---"
git pull origin main

# ── 2. Rebuild frontend (--no-cache to guarantee fresh build) ───
echo "--- frontend build ---"
docker compose -f "$COMPOSE_FILE" --profile build-only build --no-cache web

rm -rf /tmp/web-dist
TEMP_CONTAINER=$(docker create ratemeai-web-ru:latest)
docker cp "$TEMP_CONTAINER:/usr/share/nginx/html" /tmp/web-dist
docker rm "$TEMP_CONTAINER"

docker run --rm \
    -v ratemeai_web_dist:/usr/share/nginx/html \
    -v /tmp/web-dist:/src:ro \
    alpine sh -c "rm -rf /usr/share/nginx/html/* && cp -r /src/* /usr/share/nginx/html/"
rm -rf /tmp/web-dist

# ── 3. Rebuild and restart backend (migrations run on startup) ──
echo "--- backend build ---"
docker compose -f "$COMPOSE_FILE" up -d --build app

# ── 4. Restart nginx to pick up new config and volume content ───
echo "--- nginx restart ---"
docker compose -f "$COMPOSE_FILE" restart nginx

# ── 5. Wait for healthy backend ─────────────────────────────────
echo "--- health check ---"
for i in 1 2 3 4 5 6 7 8; do
    sleep 5
    RESP=$(curl -sf "$DOMAIN/health" 2>/dev/null || echo "FAIL")
    echo "  attempt $i: $RESP"
    if echo "$RESP" | grep -q '"ok"'; then
        echo "=== Deploy successful: SHA=$SHORT_SHA ==="
        docker compose -f "$COMPOSE_FILE" ps
        exit 0
    fi
done

echo "ERROR: health check failed after 8 attempts"
docker compose -f "$COMPOSE_FILE" logs --tail=40 app
exit 1
