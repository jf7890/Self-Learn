#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
[ "$(id -u)" -eq 0 ] || { echo "Run as root" >&2; exit 1; }
[ -f .env ] || { echo "Missing .env" >&2; exit 1; }

command -v nginx >/dev/null || {
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y nginx
}

npm --prefix frontend ci
npm --prefix frontend run build
install -d -m 755 /var/www/selflearn
cp -a frontend/dist/. /var/www/selflearn/
find /var/www/selflearn -type d -exec chmod 755 {} +
find /var/www/selflearn -type f -exec chmod 644 {} +

install -m 644 deploy/selflearn-api.service /etc/systemd/system/selflearn-api.service
install -m 644 deploy/nginx-selflearn.conf /etc/nginx/sites-available/selflearn
ln -sfn /etc/nginx/sites-available/selflearn /etc/nginx/sites-enabled/selflearn
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl daemon-reload
systemctl enable --now selflearn-api.service nginx.service
systemctl restart selflearn-api.service
systemctl reload nginx.service

curl -fsS http://127.0.0.1:8000/health >/dev/null
curl -fsS http://127.0.0.1:4173/api/health >/dev/null
echo "Self Learn production deployment is healthy."
