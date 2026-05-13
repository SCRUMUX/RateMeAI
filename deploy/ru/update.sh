#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────────────────────────────────────────────
# RU edge server deployment script (v1.62 — no VPS bot).
#
# Contract:
#   1. Cert is ALREADY in place at /etc/letsencrypt/live/ailookstudio.ru/
#      with SAN covering ailookstudio.ru + www.ailookstudio.ru.
#      If absent → operator must run ``deploy/ru/bootstrap-certs.sh``.
#      This script will NOT issue or renew certs.
#   2. nginx.conf in the repo is the single source of truth for the
#      RU edge nginx server-blocks.  No "lazy include" via named volume.
#   3. update.sh is dumb: rebuild → restart → health.  No DNS branching,
#      no certbot calls, no decision-making at runtime.  All previous
#      ``maybe_dns_cutover`` logic moved to bootstrap-certs.sh.
#
# Usage:
#   sudo ./deploy/ru/update.sh              # manual (run ``git pull`` first)
#   DEPLOY_GIT_SHA=abc123 ./deploy/ru/update.sh  # CI passes SHA
#
# Provisioning notes (also in deploy/ru/README.md):
#   * env-var sync to .env.ru (INTERNAL_API_KEY, ADMIN_EMAILS,
#     DEPLOYMENT_MODE, MARKET_ID, OAuth creds, …) is done in the
#     deploy-ru CI step BEFORE this script runs.
#   * ``git pull origin main`` is also done by CI in the parent
#     bash, NOT here.  Reason: bash holds the FD on the running
#     update.sh open, so any function added in the new commit would
#     stay unreachable for one whole deploy if we pulled mid-script
#     (the "one-deploy lag" bug from 1.55.2).  For local manual
#     deploys, run ``git pull`` yourself first.
# ────────────────────────────────────────────────────────────────

PROJECT_DIR="${PROJECT_DIR:-/opt/ratemeai}"
COMPOSE_FILE="docker-compose.ru.yml"
DOMAIN="${DOMAIN:-}"

cd "$PROJECT_DIR"

SHORT_SHA="${DEPLOY_GIT_SHA:-$(git rev-parse --short=12 HEAD)}"
export DEPLOY_GIT_SHA="$SHORT_SHA"

echo "=== RU Deploy: SHA=$SHORT_SHA ==="

# ── 0. Preflight: cert must be there before nginx starts ─────────
CERT_DIR="/etc/letsencrypt/live/ailookstudio.ru"
if [ ! -f "$CERT_DIR/fullchain.pem" ] || [ ! -f "$CERT_DIR/privkey.pem" ]; then
    cat <<'EOF' >&2
ERROR: TLS cert for ailookstudio.ru is missing on this host.

  Expected: /etc/letsencrypt/live/ailookstudio.ru/{fullchain,privkey}.pem

  Fix:
    1. Run the one-shot bootstrap (idempotent):
         sudo ./deploy/ru/bootstrap-certs.sh
       Or trigger the GitHub workflow:
         gh workflow run bootstrap-ru-cert.yml
    2. Re-run this script (or push to main to let CI redeploy).

This script intentionally does NOT issue certs — that decision lives
in bootstrap-certs.sh so update.sh stays predictable.
EOF
    exit 1
fi

# ── 1. Rebuild frontend (--no-cache to guarantee fresh build) ───
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

# ── 1b. Fix storage volume permissions ────────────────────────
echo "--- fix storage permissions ---"
docker run --rm -v ratemeai_app_storage:/app/storage alpine \
    sh -c "chmod -R 777 /app/storage 2>/dev/null; echo 'storage permissions fixed'" || true

# ── 2. Rebuild and (re)start backend (migrations run on app startup) ──
# 1.62.0 — the RU VPS no longer runs a ``bot`` service (Telegram bot
# lives only on Railway).  ``up -d --build`` still recreates ``app`` if
# the image / compose spec changed.
echo "--- backend build ---"
docker compose -f "$COMPOSE_FILE" up -d --build app

# ── 3. Reconcile nginx with the current compose spec ─────────────
# Why ``up -d nginx`` and not ``restart``: v1.61 removes the
# ``nginx_extra_conf`` named-volume mount from the nginx service.
# ``restart`` would keep the existing container with the old mount
# tree; ``up -d`` makes compose diff the service against the file
# and recreate when the spec changed.  No-op on a steady-state host.
echo "--- nginx reconcile ---"
docker compose -f "$COMPOSE_FILE" up -d nginx

# 1.62.4 — ``up -d --build app`` above recreates the app container, so
# it lands on a NEW IP in the docker bridge network.  nginx (which was
# NOT recreated because its compose spec didn't change) still has the
# OLD app IP cached in its upstream resolver from its own boot — and
# stock nginx upstream blocks resolve hostnames once at startup, not
# at request time.  Result on every deploy: nginx returns 502 with
# ``connect() failed (111: Connection refused) upstream: http://OLD_IP:8000``
# until the next time someone restarts nginx by hand.
# Forcing a restart here is cheap (~1s, no downtime visible from CDN
# retries) and deterministic: nginx re-resolves ``app`` against
# docker's embedded DNS (127.0.0.11) and points at the freshly-built
# container.
echo "--- nginx restart (refresh upstream app DNS after app rebuild) ---"
docker compose -f "$COMPOSE_FILE" restart nginx

# ── 4. Wait for healthy backend ─────────────────────────────────
echo "--- health check ---"
HEALTHY=0
for i in 1 2 3 4 5 6 7 8; do
    sleep 5
    RESP=$(docker compose -f "$COMPOSE_FILE" exec -T app curl -sf http://localhost:8000/health 2>/dev/null || echo "FAIL")
    echo "  attempt $i (local): $RESP"
    if echo "$RESP" | grep -q '"ok"'; then
        HEALTHY=1
        break
    fi
done

if [ "$HEALTHY" != "1" ]; then
    echo "ERROR: health check failed after 8 attempts"
    docker compose -f "$COMPOSE_FILE" logs --tail=40 app
    exit 1
fi

if [ -n "$DOMAIN" ]; then
    echo "  also probing $DOMAIN/health …"
    curl -sf "$DOMAIN/health" 2>/dev/null || echo "  (public domain probe failed)"
fi

# ── 5. Opportunistic legacy-volume cleanup ──────────────────────
# Once nginx has been reconciled to the v1.61 spec (no extra_conf mount),
# the named volume can be reaped.  Stays silent on freshly-provisioned
# hosts where the volume never existed.
docker volume rm ratemeai_nginx_extra_conf >/dev/null 2>&1 || true

echo "=== Deploy successful: SHA=$SHORT_SHA ==="
docker compose -f "$COMPOSE_FILE" ps
exit 0
