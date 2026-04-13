#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/defines.sh"

for app in $(get_apps); do
  echo "Starting $app..."
  (cd "$HOMELAB_DIR/$app" && docker compose up -d)
done
