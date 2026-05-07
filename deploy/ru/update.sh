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

# ── 2b. Fix storage volume permissions ────────────────────────
echo "--- fix storage permissions ---"
docker run --rm -v ratemeai_app_storage:/app/storage alpine \
    sh -c "chmod -R 777 /app/storage 2>/dev/null; echo 'storage permissions fixed'" || true

# ── 2c. Ensure provisioned env vars in .env.ru ─────────────────
# Idempotent: replaces an existing ``KEY=...`` line in place, or
# appends ``KEY=desired`` if the key is absent. No-op when the value
# already matches, so re-running this script does not churn the file.
# Runs BEFORE ``docker compose up -d`` so the new values are loaded
# when the app container restarts.
ENV_FILE="${PROJECT_DIR}/.env.ru"

ensure_env_line() {
    local key="$1"
    local desired="$2"
    if [ ! -f "$ENV_FILE" ]; then
        echo "[update.sh] WARNING: $ENV_FILE missing — cannot ensure $key"
        return 0
    fi
    if grep -q "^${key}=" "$ENV_FILE"; then
        local current
        current=$(grep "^${key}=" "$ENV_FILE" | head -n1 | cut -d= -f2-)
        if [ "$current" = "$desired" ]; then
            echo "[update.sh] $key already up-to-date — no-op"
            return 0
        fi
        echo "[update.sh] ensuring $key=$desired (replacing existing)"
        # ``|`` delimiter avoids escaping comma-separated values.
        sed -i "s|^${key}=.*|${key}=${desired}|" "$ENV_FILE"
    else
        echo "[update.sh] ensuring $key=$desired (appending)"
        echo "${key}=${desired}" >> "$ENV_FILE"
    fi
}

# Admin whitelist for ``/api/v1/admin/*`` — matched by
# ``_parse_admin_emails`` in src/api/v1/admin/auth.py against
# ``user_identities.profile_data->>'email'`` (any provider that
# stored an email: google / yandex / vk_id / apple).
# Primary (Railway) is unaffected: its env is managed by the
# ``deploy-backend`` job's ``rl_set`` calls, not this script.
ensure_env_line ADMIN_EMAILS "vladimir18kostyal@gmail.com,uk-tora@yandex.ru"

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
