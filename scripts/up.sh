#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/defines.sh"

for app in $(get_apps); do
  echo "Starting $app..."
  compose_files="-f docker-compose.yml"
  if [ "$(uname)" = "Linux" ] && [ -f "$HOMELAB_DIR/$app/docker-compose.linux.yml" ]; then
    compose_files="$compose_files -f docker-compose.linux.yml"
  fi
  if [ "${NO_ACME:-}" = "true" ] && [ -f "$HOMELAB_DIR/$app/docker-compose.no-acme.yml" ]; then
    compose_files="$compose_files -f docker-compose.no-acme.yml"
  fi
  (cd "$HOMELAB_DIR/$app" && docker compose $compose_files up -d --remove-orphans)
done
