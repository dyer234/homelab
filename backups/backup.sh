#!/bin/sh
REMOTE="b2:${B2_BUCKET:-homelab-backups}"
INTERVAL="${BACKUP_INTERVAL:-86400}"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

run_backup() {
  log "Starting backup"

  log "Backing up home-traefik/letsencrypt"
  rclone sync /data/home-traefik/letsencrypt "$REMOTE/home-traefik/letsencrypt" --verbose

  log "Backing up media-streaming/config"
  rclone sync /data/media-streaming/config "$REMOTE/media-streaming/config" --verbose

  log "Backup complete"
}

# Run once on startup
run_backup

# Then loop on the interval
log "Next backup in ${INTERVAL}s"
while true; do
  sleep "$INTERVAL"
  run_backup
  log "Next backup in ${INTERVAL}s"
done
