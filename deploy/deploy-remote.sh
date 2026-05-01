#!/usr/bin/env bash
set -euo pipefail

# Remote Docker Deployment Script
# Usage: ./deploy-remote.sh user@remote-host /path/on/remote

REMOTE_HOST="${1:?Usage: $0 user@host /remote/path}"
REMOTE_DIR="${2:?Usage: $0 user@host /remote/path}"
LOCAL_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Syncing project to $REMOTE_HOST:$REMOTE_DIR"
rsync -avz --delete \
  --exclude='venv/' \
  --exclude='.git/' \
  --exclude='__pycache__/' \
  --exclude='*.db' \
  --exclude='*.log' \
  "$LOCAL_DIR/" "$REMOTE_HOST:$REMOTE_DIR/"

echo "==> Building and running crawler on remote"
ssh "$REMOTE_HOST" "cd $REMOTE_DIR/deploy && docker compose up --build"

echo "==> Done"
