#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer as root: sudo ./setup-local.sh" >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "This installer currently supports Debian and Ubuntu only." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y ca-certificates curl ffmpeg openssl python3 python3-venv

install_node=false
if ! command -v node >/dev/null 2>&1; then
  install_node=true
else
  node_major="$(node -p 'process.versions.node.split(".")[0]')"
  [ "$node_major" -ge 20 ] || install_node=true
fi

if [ "$install_node" = true ]; then
  echo "Installing Node.js 20 LTS..."
  apt-get remove -y nodejs libnode-dev nodejs-doc 2>/dev/null || true
  apt-get --fix-broken install -y
  curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  apt-get install -y nodejs
fi

node_major="$(node -p 'process.versions.node.split(".")[0]')"
if [ "$node_major" -lt 20 ]; then
  echo "Node.js 20+ is required; found $(node --version)." >&2
  exit 1
fi

mkdir -p data courses

if [ ! -f .env ]; then
  secret="$(openssl rand -hex 32)"
  server_ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  server_ip="${server_ip:-localhost}"
  sed \
    -e "s|change-this-to-a-random-32-plus-character-string|$secret|" \
    -e "s|CORS_ORIGINS=http://localhost:4173|CORS_ORIGINS=http://$server_ip:4173|" \
    .env.example > .env
  echo "Created .env for http://$server_ip:4173"
else
  echo "Keeping existing .env"
fi

python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r server/requirements.txt
npm --prefix frontend ci

cat <<EOF

Setup complete.

1. Put course folders under: $PWD/courses/
2. Review: $PWD/.env
3. Start: ./run-local.sh
4. Open: http://${server_ip:-SERVER_IP}:4173
EOF
