#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/avaizur/3-trading-agents.git"
APP_DIR="/home/ubuntu/projects/3-trading-agents"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  git \
  python3 \
  python3-venv \
  python3-pip \
  ca-certificates

mkdir -p /home/ubuntu/projects

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi

chown -R ubuntu:ubuntu /home/ubuntu/projects

sudo -u ubuntu python3 -m venv "$APP_DIR/.venv"
sudo -u ubuntu "$APP_DIR/.venv/bin/python" -m pip install --upgrade pip
sudo -u ubuntu "$APP_DIR/.venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

cd "$APP_DIR"
sudo -u ubuntu "$APP_DIR/.venv/bin/python" -m pytest -q
