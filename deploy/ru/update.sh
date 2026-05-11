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
# Variant B rollout: until DNS for ailookstudio.ru is flipped to the
# VPS, RU traffic still lives on ru.ailookstudio.ru. To keep this
# script robust during the cut-over window we always probe health
# locally first (loopback, no DNS) and fall back to ``$DOMAIN`` only
# if the caller explicitly set one. After cut-over set
# ``DOMAIN=https://ailookstudio.ru`` to also smoke-test the public
# hostname.
DOMAIN="${DOMAIN:-}"

cd "$PROJECT_DIR"

SHORT_SHA="${DEPLOY_GIT_SHA:-$(git rev-parse --short=12 HEAD)}"
export DEPLOY_GIT_SHA="$SHORT_SHA"

echo "=== RU Deploy: SHA=$SHORT_SHA ==="

# ────────────────────────────────────────────────────────────────────
# Variant B Phase-2: idempotent DNS cut-over for ailookstudio.ru
#
# Contract:
#   * Runs after a successful backend health check.
#   * Steps are no-ops if a precondition fails: cut-over only happens
#     when DNS for ailookstudio.ru AND www.ailookstudio.ru both resolve
#     to this VPS's public IP. Otherwise we silently skip — exactly
#     what we want during the pre-DNS rollout window.
#   * Idempotent: cert and TLS-include creation are guarded by
#     existence checks. Repeated deploys do nothing extra.
#   * Failure-safe: a certbot failure (e.g. partial DNS propagation)
#     does NOT fail the whole deploy — we log a warning and exit 0
#     from the cut-over function so the next deploy can retry.
# ────────────────────────────────────────────────────────────────────
maybe_dns_cutover() {
    local primary_domain="ailookstudio.ru"
    local www_domain="www.ailookstudio.ru"
    local cert_name="$primary_domain"
    local extra_volume="ratemeai_nginx_extra_conf"
    local template="$PROJECT_DIR/deploy/ru/nginx-extra-template/ailookstudio-tls.conf"
    local email="${CERTBOT_EMAIL:-admin@ailookstudio.ru}"

    if [ ! -f "$template" ]; then
        echo "  [cut-over] template missing ($template) — skipping"
        return 0
    fi

    # 1. Public IP discovery (multi-source for resilience).
    local public_ip
    public_ip=$(curl -sf https://api.ipify.org 2>/dev/null \
                || curl -sf https://ifconfig.me 2>/dev/null \
                || echo "")
    if [ -z "$public_ip" ]; then
        echo "  [cut-over] could not determine public IP — skipping"
        return 0
    fi

    # 2. DNS resolution check for both domains. ``dig`` is preferred
    # (asks an external resolver, ignores /etc/hosts); ``getent ahostsv4``
    # is a fallback because minimal Ubuntu installs may not ship
    # dnsutils. Both return one IPv4 in $resolved_ip.
    resolve_a() {
        local name="$1"
        if command -v dig >/dev/null 2>&1; then
            dig +short +time=3 +tries=2 "$name" A 2>/dev/null \
                | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' \
                | tail -1
        else
            getent ahostsv4 "$name" 2>/dev/null | awk '{print $1; exit}'
        fi
    }
    local primary_ip www_ip
    primary_ip=$(resolve_a "$primary_domain" || echo "")
    www_ip=$(resolve_a "$www_domain" || echo "")

    if [ "$primary_ip" != "$public_ip" ]; then
        echo "  [cut-over] $primary_domain → $primary_ip (not us: $public_ip) — skipping"
        return 0
    fi
    if [ "$www_ip" != "$public_ip" ]; then
        echo "  [cut-over] $www_domain → $www_ip (not us: $public_ip) — skipping"
        return 0
    fi

    echo "  [cut-over] DNS for $primary_domain and $www_domain points to $public_ip — proceeding"

    # 3. Issue cert if absent. webroot lives in the certbot_www volume,
    # which nginx already serves under /.well-known/acme-challenge/
    # for all three RU domains (see nginx.conf :80 server-block).
    if [ ! -d "/etc/letsencrypt/live/$cert_name" ]; then
        echo "  [cut-over] requesting Let's Encrypt cert for $primary_domain + $www_domain …"
        if ! docker run --rm \
                -v /etc/letsencrypt:/etc/letsencrypt \
                -v ratemeai_certbot_www:/var/www/certbot \
                certbot/certbot certonly \
                    --webroot --webroot-path=/var/www/certbot \
                    -d "$primary_domain" -d "$www_domain" \
                    --cert-name "$cert_name" \
                    --email "$email" \
                    --agree-tos --no-eff-email --non-interactive; then
            echo "  [cut-over] WARN: certbot failed — leaving cut-over for next deploy"
            return 0
        fi
    else
        echo "  [cut-over] cert /etc/letsencrypt/live/$cert_name already present"
    fi

    # 4. Drop the TLS server-block into the named volume nginx mounts
    # at /etc/nginx/conf.d/extra/. nginx.conf has a glob include that
    # picks it up on next reload.
    echo "  [cut-over] installing TLS include into $extra_volume …"
    docker run --rm \
        -v "$extra_volume:/dst" \
        -v "$template:/src.conf:ro" \
        alpine sh -c "cp /src.conf /dst/ailookstudio-tls.conf && chmod 644 /dst/ailookstudio-tls.conf"

    # 5. Validate and reload nginx. If validation fails we DO NOT pull
    # the include back — better to surface the error loudly via
    # subsequent CI runs than to silently stay un-cut-over.
    if ! docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -t; then
        echo "  [cut-over] ERROR: nginx -t failed — manual intervention required"
        return 1
    fi
    docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -s reload

    # 6. Public smoke test on the new domain.
    sleep 2
    local http_code
    http_code=$(curl -sk -o /dev/null -w "%{http_code}" "https://$primary_domain/health" || echo "000")
    if [ "$http_code" = "200" ]; then
        echo "  [cut-over] ✅ https://$primary_domain/health → 200"
    else
        echo "  [cut-over] WARN: https://$primary_domain/health → $http_code (cert may still be warming up)"
    fi
    return 0
}

# ────────────────────────────────────────────────────────────────────
# Ensure the legacy ru.ailookstudio.ru server-block is installed in
# the nginx_extra_conf volume. This is the SPA+API block by default;
# when RU_LEGACY_REDIRECT_ENABLED=1 we install the 301 variant
# instead. Either way the volume holds exactly one ru-legacy*.conf
# at a time, so nginx never sees a duplicate :443 + ru.ailookstudio.ru
# server-block.
# ────────────────────────────────────────────────────────────────────
ensure_ru_legacy_block() {
    local extra_volume="ratemeai_nginx_extra_conf"
    local templates_dir="$PROJECT_DIR/deploy/ru/nginx-extra-template"
    local spa_template="$templates_dir/ru-legacy.conf"
    local redirect_template="$templates_dir/ru-legacy-redirect.conf"
    local desired
    local desired_basename

    if [ "${RU_LEGACY_REDIRECT_ENABLED:-0}" = "1" ]; then
        desired="$redirect_template"
        desired_basename="ru-legacy-redirect.conf"
    else
        desired="$spa_template"
        desired_basename="ru-legacy.conf"
    fi

    if [ ! -f "$desired" ]; then
        echo "  [ru-legacy] template missing ($desired) — skipping"
        return 0
    fi

    echo "  [ru-legacy] installing $desired_basename (mode: ${RU_LEGACY_REDIRECT_ENABLED:-spa})"
    # Remove the alternative file first, then drop in the chosen one.
    docker run --rm \
        -v "$extra_volume:/dst" \
        -v "$desired:/src.conf:ro" \
        alpine sh -c "
            rm -f /dst/ru-legacy.conf /dst/ru-legacy-redirect.conf
            cp /src.conf /dst/$desired_basename
            chmod 644 /dst/$desired_basename
        "
}

# Note (1.55.4 + cms-cutover follow-up):
#   * env-var provisioning (INTERNAL_API_KEY, ADMIN_EMAILS, DEPLOYMENT_MODE,
#     MARKET_ID, OAuth creds, ...) lives in the ``deploy-ru`` GitHub Actions
#     job before this script runs.
#   * ``git pull origin main`` ALSO lives in the CI bash, NOT here. Reason:
#     bash opens a FD on /opt/ratemeai/deploy/ru/update.sh at start; if the
#     pull happens INSIDE update.sh, bash keeps reading the previous inode
#     and any function added in the new commit (e.g. ``maybe_dns_cutover``)
#     stays unreachable for one whole deploy. Pulling in the parent CI bash
#     means this script is always read AFTER the new contents land on disk.
#   * For local manual runs (``sudo ./deploy/ru/update.sh``) make sure to
#     ``git pull`` yourself first.

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

# ── 2. Rebuild and restart backend (migrations run on startup) ──
echo "--- backend build ---"
docker compose -f "$COMPOSE_FILE" up -d --build app

# ── 2b. Install legacy ru.ailookstudio.ru server-block (SPA or 301)
echo "--- ru-legacy server-block ---"
ensure_ru_legacy_block

# ── 3. Restart nginx to pick up new config and volume content ───
echo "--- nginx restart ---"
docker compose -f "$COMPOSE_FILE" restart nginx

# ── 4. Wait for healthy backend ─────────────────────────────────
echo "--- health check ---"
for i in 1 2 3 4 5 6 7 8; do
    sleep 5
    # Always probe the in-cluster app container — DNS-independent and
    # exactly mirrors the docker compose ``healthcheck:`` directive.
    RESP=$(docker compose -f "$COMPOSE_FILE" exec -T app curl -sf http://localhost:8000/health 2>/dev/null || echo "FAIL")
    echo "  attempt $i (local): $RESP"
    if echo "$RESP" | grep -q '"ok"'; then
        if [ -n "$DOMAIN" ]; then
            echo "  also probing $DOMAIN/health …"
            curl -sf "$DOMAIN/health" 2>/dev/null || echo "  (public domain probe failed — DNS may still be propagating)"
        fi
        echo ""
        echo "--- DNS cut-over check (ailookstudio.ru) ---"
        # No-op until DNS for ailookstudio.ru is flipped to this VPS.
        # See maybe_dns_cutover() preamble for full contract.
        maybe_dns_cutover || echo "  [cut-over] non-fatal warning above"
        echo "=== Deploy successful: SHA=$SHORT_SHA ==="
        docker compose -f "$COMPOSE_FILE" ps
        exit 0
    fi
done

echo "ERROR: health check failed after 8 attempts"
docker compose -f "$COMPOSE_FILE" logs --tail=40 app
exit 1
