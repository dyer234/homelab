#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/defines.sh"

for app in $(get_apps); do
  echo "Starting $app..."
  compose_files="-f docker-compose.yml"
  if [ -e /dev/dri ] && [ -f "$HOMELAB_DIR/$app/docker-compose.gpu.yml" ]; then
    compose_files="$compose_files -f docker-compose.gpu.yml"
  fi
  (cd "$HOMELAB_DIR/$app" && docker compose $compose_files up -d)
done
