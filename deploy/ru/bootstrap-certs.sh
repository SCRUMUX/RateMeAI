#!/usr/bin/env bash
set -euo pipefail

# ────────────────────────────────────────────────────────────────────────
# RU edge: one-shot Let's Encrypt bootstrap.
#
# Runs ONCE on a fresh VPS — or re-runs after a domain change — to make
# /etc/letsencrypt/live/ailookstudio.ru/ available with a SAN that
# covers BOTH ailookstudio.ru and www.ailookstudio.ru.  After that the
# routine update.sh can safely reference the cert paths in nginx.conf
# without any "lazy include" tricks.
#
# Idempotent: if the right cert already exists, exits 0 without action.
#
# Usage on the VPS (or via GitHub Action ``Bootstrap RU edge cert``):
#     sudo ./deploy/ru/bootstrap-certs.sh
#
# What the script does:
#   1. Verifies prerequisites (docker, public IP).
#   2. Short-circuits if /etc/letsencrypt/live/ailookstudio.ru/cert.pem
#      already lists both ailookstudio.ru and www.ailookstudio.ru in SAN.
#   3. Ensures something is listening on :80 to answer ACME http-01:
#        - if the project's nginx container is up and serving
#          /.well-known/acme-challenge/ — use it as-is;
#        - otherwise start a minimal throw-away nginx that serves the
#          certbot webroot volume and tear it down at the end.
#   4. Runs ``certbot certonly --webroot`` for ailookstudio.ru + www.
#   5. Optional cleanup: ``certbot delete --cert-name ru.ailookstudio.ru``
#      to drop the legacy lineage from the pre-cutover era so it can
#      never accidentally be picked up by nginx again.
#   6. Re-verifies the SAN and prints the next step.
#
# Failure modes are NOT swallowed.  If anything in step 3/4 fails the
# script exits non-zero so the operator (or the wrapping GitHub Action)
# sees a red status — we don't want a silent "WARN: certbot failed"
# like in the old maybe_dns_cutover() that left the VPS half-broken.
# ────────────────────────────────────────────────────────────────────────

PROJECT_DIR="${PROJECT_DIR:-/opt/ratemeai}"
COMPOSE_FILE="${PROJECT_DIR}/docker-compose.ru.yml"
CERT_NAME="ailookstudio.ru"
PRIMARY_DOMAIN="ailookstudio.ru"
WWW_DOMAIN="www.ailookstudio.ru"
LEGACY_CERT_NAME="ru.ailookstudio.ru"
EMAIL="${CERTBOT_EMAIL:-admin@ailookstudio.ru}"
CERTBOT_WWW_VOLUME="ratemeai_certbot_www"
LE_DIR="/etc/letsencrypt"
LIVE_DIR="${LE_DIR}/live/${CERT_NAME}"
TMP_NGINX_NAME="bootstrap-certbot-nginx"

cd "$PROJECT_DIR"

log() { printf '[bootstrap-certs] %s\n' "$*"; }

# ---- helpers ----------------------------------------------------------

cert_has_san() {
    # $1 lineage, $2 expected DNS label.  Returns 0 if cert.pem in the
    # given lineage has DNS:<label> in its SubjectAltName.  Uses the
    # alpine/openssl image so we don't depend on host openssl.
    local lineage="$1"
    local expect="$2"
    local cert_path="${LE_DIR}/live/${lineage}/cert.pem"
    if [ ! -f "$cert_path" ]; then
        return 1
    fi
    docker run --rm -v "${LE_DIR}:${LE_DIR}" \
        alpine/openssl x509 -in "$cert_path" -noout -ext subjectAltName 2>/dev/null \
        | grep -oE 'DNS:[A-Za-z0-9.-]+' \
        | grep -qx "DNS:${expect}"
}

project_nginx_serves_acme() {
    # True iff the docker-compose nginx container is up.  Our nginx.conf
    # serves /.well-known/acme-challenge/ from the certbot_www volume on
    # :80 for ailookstudio.ru / www.ailookstudio.ru.
    docker compose -f "$COMPOSE_FILE" ps nginx 2>/dev/null \
        | grep -qE '(\bUp\b|\brunning\b)'
}

start_temp_nginx() {
    log "starting throw-away nginx on :80 for ACME challenge"
    # nginx:alpine + a one-liner default.conf is enough.  Bind to the
    # named certbot_www volume so certbot's webroot challenge lands in
    # the same place nginx will serve from.
    docker run -d --rm --name "$TMP_NGINX_NAME" \
        -p 80:80 \
        -v "${CERTBOT_WWW_VOLUME}:/var/www/certbot" \
        nginx:alpine sh -c '
            cat > /etc/nginx/conf.d/default.conf <<NGINX_EOF
server {
    listen 80;
    server_name _;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 404; }
}
NGINX_EOF
            exec nginx -g "daemon off;"
        ' >/dev/null
    # Give nginx a beat to settle.
    sleep 2
}

stop_temp_nginx() {
    if docker ps --format '{{.Names}}' | grep -qx "$TMP_NGINX_NAME"; then
        log "stopping throw-away nginx"
        docker stop "$TMP_NGINX_NAME" >/dev/null || true
    fi
}

# ---- preflight --------------------------------------------------------

if ! command -v docker >/dev/null 2>&1; then
    log "ERROR: docker not installed on this host"
    exit 1
fi

if [ ! -f "$COMPOSE_FILE" ]; then
    log "ERROR: ${COMPOSE_FILE} not found — wrong PROJECT_DIR?"
    exit 1
fi

# Make sure the named volume exists; certbot will write the challenge
# files there and our (real or temp) nginx will serve them.  ``docker
# volume create`` is idempotent.
docker volume create "$CERTBOT_WWW_VOLUME" >/dev/null

# ---- idempotency short-circuit ----------------------------------------

if cert_has_san "$CERT_NAME" "$PRIMARY_DOMAIN" \
   && cert_has_san "$CERT_NAME" "$WWW_DOMAIN"; then
    log "cert ${LIVE_DIR} already covers ${PRIMARY_DOMAIN} + ${WWW_DOMAIN} — nothing to do"
    # Still take the chance to clean up the legacy lineage if it lingers.
    if [ -d "${LE_DIR}/live/${LEGACY_CERT_NAME}" ]; then
        log "removing legacy cert lineage ${LEGACY_CERT_NAME}"
        docker run --rm -v "${LE_DIR}:${LE_DIR}" \
            certbot/certbot delete --cert-name "$LEGACY_CERT_NAME" --non-interactive \
            >/dev/null 2>&1 || true
    fi
    exit 0
fi

# ---- issue --------------------------------------------------------------

log "cert at ${LIVE_DIR} is absent or doesn't cover both names — issuing"

OWNS_TEMP_NGINX=0
if ! project_nginx_serves_acme; then
    start_temp_nginx
    OWNS_TEMP_NGINX=1
else
    log "project nginx is already up; using it for ACME challenge"
fi

trap 'if [ "$OWNS_TEMP_NGINX" = "1" ]; then stop_temp_nginx; fi' EXIT

log "certbot certonly --webroot for ${PRIMARY_DOMAIN} + ${WWW_DOMAIN}"
docker run --rm \
    -v "${LE_DIR}:${LE_DIR}" \
    -v "${CERTBOT_WWW_VOLUME}:/var/www/certbot" \
    certbot/certbot certonly \
        --webroot --webroot-path=/var/www/certbot \
        -d "$PRIMARY_DOMAIN" -d "$WWW_DOMAIN" \
        --cert-name "$CERT_NAME" \
        --email "$EMAIL" \
        --agree-tos --no-eff-email --non-interactive

# ---- cleanup legacy ---------------------------------------------------

if [ -d "${LE_DIR}/live/${LEGACY_CERT_NAME}" ]; then
    log "removing legacy cert lineage ${LEGACY_CERT_NAME}"
    docker run --rm -v "${LE_DIR}:${LE_DIR}" \
        certbot/certbot delete --cert-name "$LEGACY_CERT_NAME" --non-interactive \
        >/dev/null 2>&1 || true
fi

# ---- verify -----------------------------------------------------------

if cert_has_san "$CERT_NAME" "$PRIMARY_DOMAIN" \
   && cert_has_san "$CERT_NAME" "$WWW_DOMAIN"; then
    log "OK: ${LIVE_DIR} now covers ${PRIMARY_DOMAIN} + ${WWW_DOMAIN}"
    log "next: trigger CI deploy (push to main) or run sudo ./deploy/ru/update.sh"
    exit 0
else
    log "ERROR: certbot reported success but SAN check still fails"
    log "  inspect ${LIVE_DIR}/cert.pem manually with:"
    log "  docker run --rm -v ${LE_DIR}:${LE_DIR} alpine/openssl x509 \\"
    log "    -in ${LIVE_DIR}/cert.pem -noout -text"
    exit 1
fi
