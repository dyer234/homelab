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
  # Apps whose secrets live in 1Password carry a committed 1pass.env of op://
  # references; run compose under `op run` so they resolve into the environment
  # (compose reads ${VAR} from the process env, no .env needed). Apps without
  # one still use their .env as before.
  # ${runner[@]+...} rather than "${runner[@]}": bash 3.2 (macOS) treats an
  # empty array as unbound under set -u.
  runner=()
  if [ -f "$HOMELAB_DIR/$app/1pass.env" ]; then
    runner=(op run --env-file=1pass.env --)
  fi
  (cd "$HOMELAB_DIR/$app" && ${runner[@]+"${runner[@]}"} docker compose $compose_files up -d --remove-orphans)
done
