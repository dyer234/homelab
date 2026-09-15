#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/defines.sh"

# Host toggles (NO_ACME) come from homelab.local.env unless already exported.
if [ -z "${NO_ACME:-}" ] && [ -f "$HOMELAB_DIR/homelab.local.env" ]; then
  NO_ACME="$(sed -n 's/^NO_ACME=//p' "$HOMELAB_DIR/homelab.local.env")"
fi

for app in $(get_apps); do
  echo "Starting $app..."
  compose_files="-f docker-compose.yml"
  if [ "$(uname)" = "Linux" ] && [ -f "$HOMELAB_DIR/$app/docker-compose.linux.yml" ]; then
    compose_files="$compose_files -f docker-compose.linux.yml"
  fi
  if [ "${NO_ACME:-}" = "true" ] && [ -f "$HOMELAB_DIR/$app/docker-compose.no-acme.yml" ]; then
    compose_files="$compose_files -f docker-compose.no-acme.yml"
  fi
  env_files=($(compose_env_files "$app"))
  # Apps whose secrets live in 1Password carry a committed 1pass.env of op://
  # references; run compose under `op run` so they resolve into the environment
  # (compose reads ${VAR} from the process env, which beats every env file).
  # ${runner[@]+...} rather than "${runner[@]}": bash 3.2 (macOS) treats an
  # empty array as unbound under set -u.
  runner=()
  if [ -f "$HOMELAB_DIR/$app/1pass.env" ]; then
    runner=(op run --env-file=1pass.env --)
  fi
  (cd "$HOMELAB_DIR/$app" && ${runner[@]+"${runner[@]}"} docker compose "${env_files[@]}" $compose_files up -d --remove-orphans)
done
