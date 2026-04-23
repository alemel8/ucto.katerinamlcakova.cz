#!/usr/bin/env bash
# ─── VPS Deployment Script (PM2 + Git) ───────────────────────────────────────
# Usage: ./deploy.sh [user@vps-ip]
# Default target: root@89.221.219.220
#
# Předpoklady na VPS: git, Python 3.10+, Node.js 18+
# Spouštěj z libovolného místa – nasazuje vždy z Gitu.

set -euo pipefail

TARGET="${1:-root@89.221.219.220}"
REPO="git@github-ucto:alemel8/ucto.katerinamlcakova.cz.git"
REMOTE_DIR="/opt/vytezovani-faktur"
DOMAIN="ucto.katerinamlcakova.cz"

echo "==> Deploying $REPO → $TARGET:$REMOTE_DIR"

# ── 1. Check .env exists on VPS (before touching anything) ────────────────────
ENV_EXISTS=$(ssh "$TARGET" "[ -f $REMOTE_DIR/backend/.env ] && echo yes || echo no" 2>/dev/null || echo no)
if [[ "$ENV_EXISTS" == "no" ]]; then
  echo ""
  echo "!! POZOR: $REMOTE_DIR/backend/.env neexistuje na VPS."
  echo "   Při prvním nasazení ho vytvoř takto:"
  echo ""
  echo "   ssh $TARGET"
  echo "   mkdir -p $REMOTE_DIR/backend"
  echo "   nano $REMOTE_DIR/backend/.env    # viz backend/.env.example"
  echo ""
  echo "   Poté znovu spusť: ./deploy.sh"
  exit 1
fi

# ── 2. Remote setup ───────────────────────────────────────────────────────────
ssh "$TARGET" bash << REMOTE
set -euo pipefail

# ── Git ────────────────────────────────────────────────────────────────────
if ! command -v git &>/dev/null; then
  apt-get update -q && apt-get install -y -q git
fi

# Klonuj nebo aktualizuj repozitář
if [ ! -d "$REMOTE_DIR/.git" ]; then
  echo "Cloning repository..."
  # Přejmenuj existující adresář, klonuj, obnov .env
  if [ -d "$REMOTE_DIR" ]; then
    mv "$REMOTE_DIR" "${REMOTE_DIR}.bak"
  fi
  git clone $REPO $REMOTE_DIR
  # Obnov .env ze zálohy pokud existoval
  if [ -f "${REMOTE_DIR}.bak/backend/.env" ]; then
    cp "${REMOTE_DIR}.bak/backend/.env" "$REMOTE_DIR/backend/.env"
  fi
  rm -rf "${REMOTE_DIR}.bak"
else
  echo "Pulling latest changes..."
  git -C $REMOTE_DIR pull --ff-only
fi

# ── Node.js (LTS) ──────────────────────────────────────────────────────────
if ! command -v node &>/dev/null; then
  echo "Installing Node.js LTS..."
  curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -
  apt-get install -y -q nodejs
fi

# ── PM2 ────────────────────────────────────────────────────────────────────
if ! command -v pm2 &>/dev/null; then
  echo "Installing PM2..."
  npm install -g pm2
  pm2 startup systemd -u root --hp /root | tail -1 | bash
fi

# ── Python venv + dependencies ─────────────────────────────────────────────
cd $REMOTE_DIR/backend
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -r requirements.txt -q

# ── Frontend build ─────────────────────────────────────────────────────────
cd $REMOTE_DIR/frontend
npm ci --silent
npm run build

# ── Nginx vhost ────────────────────────────────────────────────────────────
if ! command -v nginx &>/dev/null; then
  echo "Installing Nginx..."
  apt-get update -q && apt-get install -y -q nginx
fi

cp $REMOTE_DIR/vps/nginx-vhost.conf /etc/nginx/sites-available/$DOMAIN
ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/$DOMAIN
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# ── SSL (Let's Encrypt) ────────────────────────────────────────────────────
if ! command -v certbot &>/dev/null; then
  echo "Installing Certbot..."
  apt-get install -y -q certbot python3-certbot-nginx
fi
if [ ! -d /etc/letsencrypt/live/$DOMAIN ]; then
  certbot --nginx -d $DOMAIN --non-interactive --agree-tos -m admin@katerinamlcakova.cz
  systemctl reload nginx
fi

# ── Start / restart PM2 backend ────────────────────────────────────────────
cd $REMOTE_DIR
pm2 reload ecosystem.config.js --update-env 2>/dev/null || pm2 start ecosystem.config.js
pm2 save

echo ""
echo "==> Deployment complete!"
pm2 list
REMOTE

echo ""
echo "✓ Hotovo. Aplikace běží na https://$DOMAIN"

