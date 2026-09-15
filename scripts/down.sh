#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/defines.sh"

for app in $(get_apps); do
  echo "Stopping $app..."
  # Same env files as up.sh: compose refuses to parse a project whose required
  # variables are unset, even just to stop it.
  env_files=($(compose_env_files "$app"))
  (cd "$HOMELAB_DIR/$app" && docker compose "${env_files[@]}" stop)
done
