#!/usr/bin/env bash

# Root of the homelab project
HOMELAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Get all directories that contain a docker-compose.yml. home-traefik comes
# first: it creates the traefik-public network every other stack declares as
# external, so on a fresh host (or after the network is recreated) nothing
# else can start before it.
get_apps() {
  [ -f "$HOMELAB_DIR/home-traefik/docker-compose.yml" ] && echo home-traefik
  for dir in "$HOMELAB_DIR"/*/; do
    if [ -f "$dir/docker-compose.yml" ] && [ "$(basename "$dir")" != home-traefik ]; then
      basename "$dir"
    fi
  done
}

# Env files for docker compose in $1's directory, lowest to highest precedence
# (see homelab.env). Compose stops auto-loading <app>/.env once given any
# --env-file, hence the explicit third entry. Emits one flag per line for
# mapfile / "$(...)" use.
compose_env_files() {
  echo "--env-file=$HOMELAB_DIR/homelab.env"
  [ -f "$HOMELAB_DIR/homelab.local.env" ] && echo "--env-file=$HOMELAB_DIR/homelab.local.env"
  [ -f "$HOMELAB_DIR/$1/.env" ] && echo "--env-file=$HOMELAB_DIR/$1/.env"
  return 0
}
