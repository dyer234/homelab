#!/usr/bin/env bash

# Root of the homelab project
HOMELAB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Get all directories that contain a docker-compose.yml
get_apps() {
  for dir in "$HOMELAB_DIR"/*/; do
    if [ -f "$dir/docker-compose.yml" ]; then
      basename "$dir"
    fi
  done
}
