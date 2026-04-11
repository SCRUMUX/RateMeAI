#!/usr/bin/env bash
set -euo pipefail

# ============================================================
# RU Edge Server Setup Script (Ubuntu 22.04)
# ============================================================
# Run as root or with sudo:
#   chmod +x deploy/ru/setup.sh && sudo ./deploy/ru/setup.sh
#
# Prerequisites:
#   - Ubuntu 22.04 with SSH access
#   - Domain ru.ailookstudio.ru pointing to this server's IP
#   - .env.ru filled out (copy from .env.ru.example)
# ============================================================

DOMAIN="${DOMAIN:-ru.ailookstudio.ru}"
EMAIL="${CERTBOT_EMAIL:-admin@ailookstudio.ru}"
PROJECT_DIR="${PROJECT_DIR:-/opt/ratemeai}"

echo "=== RateMEAI RU Edge Server Setup ==="
echo "Domain: $DOMAIN"
echo "Project dir: $PROJECT_DIR"
echo ""

# --- 1. System updates ---
echo "[1/7] Updating system packages..."
apt-get update -y
apt-get upgrade -y
apt-get install -y curl git ufw software-properties-common

# --- 2. Install Docker ---
echo "[2/7] Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    echo "Docker installed."
else
    echo "Docker already installed."
fi

if ! command -v docker compose &> /dev/null && ! docker compose version &> /dev/null; then
    apt-get install -y docker-compose-plugin
fi

# --- 3. Firewall ---
echo "[3/7] Configuring firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (certbot + redirect)
ufw allow 443/tcp   # HTTPS
ufw --force enable
echo "Firewall configured (22, 80, 443 open)."

# --- 4. Clone/update project ---
echo "[4/7] Setting up project directory..."
if [ -d "$PROJECT_DIR/.git" ]; then
    cd "$PROJECT_DIR"
    git pull origin main
    echo "Project updated."
else
    echo "Please clone the project to $PROJECT_DIR:"
    echo "  git clone <your-repo-url> $PROJECT_DIR"
    echo "  or copy the project files manually."
    echo ""
    if [ ! -d "$PROJECT_DIR" ]; then
        mkdir -p "$PROJECT_DIR"
    fi
fi

cd "$PROJECT_DIR"

# --- 5. SSL Certificate (Let's Encrypt) ---
echo "[5/7] Setting up SSL certificate..."

# Create temp nginx for certbot challenge (no SSL yet)
mkdir -p /tmp/certbot-nginx
cat > /tmp/certbot-nginx/default.conf <<NGINX_EOF
server {
    listen 80;
    server_name $DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 'Setting up SSL...';
        add_header Content-Type text/plain;
    }
}
NGINX_EOF

mkdir -p /var/www/certbot

# Stop any existing containers on port 80
docker compose -f docker-compose.ru.yml down 2>/dev/null || true

# Run temp nginx for ACME challenge
docker run -d --name certbot-nginx \
    -p 80:80 \
    -v /tmp/certbot-nginx/default.conf:/etc/nginx/conf.d/default.conf:ro \
    -v /var/www/certbot:/var/www/certbot \
    nginx:alpine

# Get certificate
docker run --rm \
    -v /etc/letsencrypt:/etc/letsencrypt \
    -v /var/www/certbot:/var/www/certbot \
    certbot/certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        -d "$DOMAIN" \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --non-interactive

# Cleanup temp nginx
docker stop certbot-nginx && docker rm certbot-nginx
rm -rf /tmp/certbot-nginx

echo "SSL certificate obtained for $DOMAIN."

# --- 6. Build and deploy ---
echo "[6/7] Building and starting services..."

if [ ! -f "$PROJECT_DIR/.env.ru" ]; then
    echo "ERROR: $PROJECT_DIR/.env.ru not found!"
    echo "Copy .env.ru.example to .env.ru and fill in the values before continuing."
    exit 1
fi

# Copy SSL certs to Docker volume location
docker compose -f docker-compose.ru.yml down 2>/dev/null || true

# Build the frontend image with RU API URL
docker compose -f docker-compose.ru.yml --profile build-only build web

# Copy built frontend to volume
TEMP_CONTAINER=$(docker create ratemeai-web-ru:latest)
docker cp "$TEMP_CONTAINER:/usr/share/nginx/html" /tmp/web-dist
docker rm "$TEMP_CONTAINER"

# Create certbot volume with certs
docker volume create ratemeai_certbot_conf 2>/dev/null || true
docker run --rm \
    -v ratemeai_certbot_conf:/etc/letsencrypt \
    -v /etc/letsencrypt:/host-certs:ro \
    alpine sh -c "cp -r /host-certs/* /etc/letsencrypt/"

# Create web_dist volume with frontend files
docker volume create ratemeai_web_dist 2>/dev/null || true
docker run --rm \
    -v ratemeai_web_dist:/usr/share/nginx/html \
    -v /tmp/web-dist:/src:ro \
    alpine sh -c "cp -r /src/* /usr/share/nginx/html/"

rm -rf /tmp/web-dist

# Build backend and start all services
docker compose -f docker-compose.ru.yml up -d --build

echo "Services started."

# --- 7. Setup certbot auto-renewal cron ---
echo "[7/7] Setting up SSL auto-renewal..."
CRON_CMD="0 3 * * 1 cd $PROJECT_DIR && docker compose -f docker-compose.ru.yml run --rm certbot renew && docker compose -f docker-compose.ru.yml exec nginx nginx -s reload"
(crontab -l 2>/dev/null | grep -v "certbot renew" || true; echo "$CRON_CMD") | crontab -
echo "Certbot auto-renewal cron added (weekly at 3am Monday)."

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Services running:"
docker compose -f docker-compose.ru.yml ps
echo ""
echo "Health check:"
echo "  curl -s https://$DOMAIN/health"
echo ""
echo "Useful commands:"
echo "  docker compose -f docker-compose.ru.yml logs -f app     # API logs"
echo "  docker compose -f docker-compose.ru.yml logs -f nginx   # Nginx logs"
echo "  docker compose -f docker-compose.ru.yml restart          # Restart all"
echo "  docker compose -f docker-compose.ru.yml down             # Stop all"
