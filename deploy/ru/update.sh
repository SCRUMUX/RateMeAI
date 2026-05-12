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
            # 1.60.3: запрашиваем напрямую у публичных резолверов
            # (8.8.8.8, 1.1.1.1) в обход системного резолвера VPS,
            # потому что у Selectel / некоторых VPS systemd-resolved
            # держит длинный кэш для apex-доменов и видит старый
            # Vercel-edge IP даже после смены A-записи на 60-сек TTL.
            local ip
            for resolver in 8.8.8.8 1.1.1.1; do
                ip=$(dig "@${resolver}" +short +time=3 +tries=2 "$name" A 2>/dev/null \
                    | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' \
                    | tail -1)
                if [ -n "$ip" ]; then
                    echo "$ip"
                    return 0
                fi
            done
            # Fallback: системный резолвер, если оба публичных недоступны
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

    # 3. Issue cert if absent OR if existing one doesn't cover
    # $primary_domain in SAN.  Why the SAN check matters: a previous
    # certbot run could have created /etc/letsencrypt/live/$cert_name/
    # before DNS was actually pointing at us — challenge failed but
    # certbot still keeps the lineage directory, or a stale cert from
    # a manual debug session may live there.  Without the SAN check
    # we'd loop forever with "cert already present" while nginx keeps
    # serving the wrong certificate (mismatched CN → browser shows
    # ERR_CERT_COMMON_NAME_INVALID).
    #
    # webroot for challenges lives in the certbot_www volume, which
    # nginx already serves under /.well-known/acme-challenge/ for all
    # three RU domains (see nginx.conf :80 server-block).
    cert_san_includes() {
        # $1 = lineage name (e.g. ailookstudio.ru)
        # $2 = expected DNS name (e.g. ailookstudio.ru)
        local lineage="$1"
        local expect="$2"
        local cert_path="/etc/letsencrypt/live/$lineage/cert.pem"
        # SubjectAltName format: "DNS:foo, DNS:bar".  We match the
        # whole label to avoid partial matches (ailookstudio.ru must
        # NOT match against ru.ailookstudio.ru).
        docker run --rm -v /etc/letsencrypt:/etc/letsencrypt \
            alpine/openssl x509 -in "$cert_path" -noout -ext subjectAltName 2>/dev/null \
            | grep -oE 'DNS:[A-Za-z0-9.-]+' \
            | grep -qx "DNS:$expect"
    }

    local need_issue=0
    if [ ! -d "/etc/letsencrypt/live/$cert_name" ]; then
        need_issue=1
    elif ! cert_san_includes "$cert_name" "$primary_domain"; then
        echo "  [cut-over] existing cert at /etc/letsencrypt/live/$cert_name does NOT cover $primary_domain — deleting and re-issuing"
        docker run --rm -v /etc/letsencrypt:/etc/letsencrypt \
            certbot/certbot delete --cert-name "$cert_name" --non-interactive || true
        need_issue=1
    else
        echo "  [cut-over] cert /etc/letsencrypt/live/$cert_name already covers $primary_domain"
    fi

    if [ "$need_issue" = "1" ]; then
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
    fi

    # 4. Drop the TLS server-block into the named volume nginx mounts
    # at /etc/nginx/conf.d/extra/.  Why a full container restart instead
    # of ``nginx -s reload``: empirically the ``include extra/*.conf;``
    # glob isn't always picked up by SIGHUP when a file is dropped into
    # a named volume from a sibling container (file appears in the
    # volume but the running nginx master keeps its cached config tree).
    # A container restart re-reads the include from scratch and is the
    # only path we've seen reliably honour the new server-block.
    echo "  [cut-over] installing TLS include into $extra_volume …"
    if ! docker run --rm \
            -v "$extra_volume:/dst" \
            -v "$template:/src.conf:ro" \
            alpine sh -c "cp /src.conf /dst/ailookstudio-tls.conf && chmod 644 /dst/ailookstudio-tls.conf && ls -la /dst/"; then
        echo "  [cut-over] ERROR: failed to copy TLS template into named volume — aborting cut-over"
        return 1
    fi

    # 5. Validate and restart nginx so the new include is honoured.
    if ! docker compose -f "$COMPOSE_FILE" exec -T nginx nginx -t; then
        echo "  [cut-over] ERROR: nginx -t failed — manual intervention required"
        return 1
    fi
    echo "  [cut-over] restarting nginx to pick up extra/ailookstudio-tls.conf …"
    docker compose -f "$COMPOSE_FILE" restart nginx

    # 5b. Diagnostic: list extra dir and the server_name lines nginx
    # actually loaded.  Helps spot the next time the include doesn't
    # apply (silently mounted empty, wrong file mode, etc.).
    echo "  [cut-over] post-restart nginx state:"
    docker compose -f "$COMPOSE_FILE" exec -T nginx ls -la /etc/nginx/conf.d/extra/ 2>&1 | sed 's/^/    /' || true
    docker compose -f "$COMPOSE_FILE" exec -T nginx sh -c "nginx -T 2>/dev/null | grep -E 'server_name|listen 443' | sort -u" 2>&1 | sed 's/^/    /' || true

    # 6. Public smoke test on the new domain.  We probe the cert
    # by name (no -k) AND via --resolve to our own public IP so the
    # check doesn't depend on whatever resolver this VPS happens to
    # cache.  Two outcomes that matter:
    #   * exit 0 + 200  → cert covers $primary_domain, nginx serves
    #     it, everything healthy.
    #   * exit 60       → cert/SNI mismatch (something is still
    #     wrong even after our SAN re-issue branch).
    sleep 2
    local http_code curl_exit
    # Capture both http_code and curl's exit code without tripping set -e.
    if http_code=$(curl -s -o /dev/null -w "%{http_code}" \
                    --resolve "$primary_domain:443:$public_ip" \
                    "https://$primary_domain/health" 2>/dev/null); then
        curl_exit=0
    else
        curl_exit=$?
    fi
    if [ "$http_code" = "200" ] && [ "$curl_exit" = "0" ]; then
        echo "  [cut-over] ✅ https://$primary_domain/health → 200 (cert OK)"
    elif [ "$curl_exit" = "60" ]; then
        echo "  [cut-over] WARN: cert validation failed for https://$primary_domain (curl exit 60). Next deploy will retry after SAN check."
    else
        echo "  [cut-over] WARN: https://$primary_domain/health → http_code=$http_code curl_exit=$curl_exit"
    fi
    return 0
}

# 1.60-fix: legacy ``ensure_ru_legacy_block`` was removed.  The original
# design split the :443 ``ru.ailookstudio.ru`` server-block out into
# ``/etc/nginx/conf.d/extra/ru-legacy.conf`` (named volume), but on the
# first deploy after the change the volume was empty for the few seconds
# between ``docker compose up app`` (which restarts the nginx container
# as a dependency) and ``ensure_ru_legacy_block`` — so nginx started
# without any :443 listener, and remote ``Connection refused`` on
# https://ru.ailookstudio.ru/health.  Решение: 443-блок для
# ``ru.ailookstudio.ru`` снова живёт прямо в ``deploy/ru/nginx.conf``
# (read-only mount из репо, всегда есть на старте).  ``extra/*.conf``
# теперь используется только для НОВОГО ``ailookstudio.ru`` TLS-блока,
# который ставит ``maybe_dns_cutover`` после DNS cut-over'а.

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

# Clean up any leftover ``extra/ru-legacy*.conf`` files from the
# 1.60.0 short-lived split (see comment above ``maybe_dns_cutover``).
# Idempotent: ``rm -f`` doesn't fail on a clean volume.
docker run --rm -v ratemeai_nginx_extra_conf:/dst alpine \
    sh -c "rm -f /dst/ru-legacy.conf /dst/ru-legacy-redirect.conf" || true

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
