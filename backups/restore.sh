#!/bin/sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOMELAB_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Load .env
if [ -f "$SCRIPT_DIR/.env" ]; then
  . "$SCRIPT_DIR/.env"
fi

BUCKET="${B2_BUCKET:-homelab-backups}"
REMOTE="b2:$BUCKET"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

echo ""
echo "This will overwrite local data with the Backblaze B2 backup from:"
echo "  Bucket: $BUCKET"
echo ""
echo "Targets:"
echo "  - $HOMELAB_DIR/home-traefik/letsencrypt/"
echo "  - $HOMELAB_DIR/media-streaming/config/"
echo ""
printf "Continue? [y/N] "
read -r confirm
case "$confirm" in
  [yY]*) ;;
  *) echo "Aborted."; exit 0 ;;
esac

log "Restoring home-traefik/letsencrypt"
docker run --rm \
  -v "$SCRIPT_DIR/rclone.conf:/opt/backup/rclone.conf:ro" \
  -v "$HOMELAB_DIR/home-traefik/letsencrypt:/data/home-traefik/letsencrypt" \
  rclone/rclone:latest \
  sync "$REMOTE/home-traefik/letsencrypt" /data/home-traefik/letsencrypt \
  --config /opt/backup/rclone.conf --verbose

log "Restoring media-streaming/config"
docker run --rm \
  -v "$SCRIPT_DIR/rclone.conf:/opt/backup/rclone.conf:ro" \
  -v "$HOMELAB_DIR/media-streaming/config:/data/media-streaming/config" \
  rclone/rclone:latest \
  sync "$REMOTE/media-streaming/config" /data/media-streaming/config \
  --config /opt/backup/rclone.conf --verbose

log "Restore complete"
