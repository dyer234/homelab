#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOMELAB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env
if [ -f "$SCRIPT_DIR/.env" ]; then
  . "$SCRIPT_DIR/.env"
fi

BUCKET="${B2_BUCKET:-homelab-backups}"
REMOTE="b2:$BUCKET"
STAGING="/tmp/restore"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

download_and_extract() {
  name="$1"
  dest="$2"

  log "Restoring $name"
  mkdir -p "$STAGING"

  # Download the latest archive for this target
  latest=$(docker run --rm \
    -v "$SCRIPT_DIR/rclone.conf:/opt/backup/rclone.conf:ro" \
    rclone/rclone:latest \
    lsf "$REMOTE/$name/" --config /opt/backup/rclone.conf \
    | sort | tail -1)

  if [ -z "$latest" ]; then
    log "No backup found for $name, skipping"
    return 1
  fi

  log "Downloading $latest"
  docker run --rm \
    -v "$SCRIPT_DIR/rclone.conf:/opt/backup/rclone.conf:ro" \
    -v "$STAGING:/staging" \
    rclone/rclone:latest \
    copy "$REMOTE/$name/$latest" /staging/ \
    --config /opt/backup/rclone.conf --verbose

  log "Extracting to $dest"
  tar xzf "$STAGING/$latest" -C "$dest"
  rm -f "$STAGING/$latest"
}

echo ""
echo "This will overwrite local data with the latest Backblaze B2 backup from:"
echo "  Bucket: $BUCKET"
echo ""
echo "Targets:"
echo "  - $HOMELAB_DIR/home-traefik/letsencrypt/"
echo "  - $HOMELAB_DIR/media-streaming/config/"
echo "  - $HOMELAB_DIR/n8n/data/"
echo "  - $HOMELAB_DIR/ai/open-webui/"
echo "  - $HOMELAB_DIR/navidrome/config/"
echo ""
printf "Continue? [y/N] "
read -r confirm
case "$confirm" in
  [yY]*) ;;
  *) echo "Aborted."; exit 0 ;;
esac

download_and_extract "home-traefik" "$HOMELAB_DIR/home-traefik/"
download_and_extract "media-streaming" "$HOMELAB_DIR/media-streaming/"
download_and_extract "n8n" "$HOMELAB_DIR/n8n/"
download_and_extract "ai" "$HOMELAB_DIR/ai/"
download_and_extract "navidrome" "$HOMELAB_DIR/navidrome/"

rm -rf "$STAGING"

log "Restore complete"
