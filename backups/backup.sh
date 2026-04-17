#!/bin/sh
REMOTE="b2:${B2_BUCKET:-homelab-backups}"
STAGING="/tmp/backups"
DATE=$(date '+%Y-%m-%d')
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-7}

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

tar_and_upload() {
  name="$1"
  src="$2"
  filter="$3"

  log "Backing up $name"
  mkdir -p "$STAGING"

  archive="$STAGING/${name}-${DATE}.tar.gz"
  if [ -n "$filter" ]; then
    tar czf "$archive" --exclude-from="$filter" -C "$(dirname "$src")" "$(basename "$src")"
  else
    tar czf "$archive" -C "$(dirname "$src")" "$(basename "$src")"
  fi

  rclone copy "$archive" "$REMOTE/$name/" --verbose
  rm -f "$archive"
}

run_backup() {
  log "Starting backup"

  tar_and_upload "home-traefik" "/data/home-traefik/letsencrypt"
  tar_and_upload "media-streaming" "/data/media-streaming/config" "/opt/backup/exclude-filters.txt"
  tar_and_upload "n8n" "/data/n8n/data" "/opt/backup/exclude-filters.txt"
  tar_and_upload "ai" "/data/ai/open-webui" "/opt/backup/exclude-filters.txt"
  tar_and_upload "navidrome" "/data/navidrome/config" "/opt/backup/exclude-filters.txt"

  rm -rf "$STAGING"

  log "Cleaning up backups older than $RETENTION_DAYS days"
  rclone delete "$REMOTE" --min-age "${RETENTION_DAYS}d" --verbose

  log "Backup complete"
}

# Run once on startup
run_backup

# Then run on the cron schedule
log "Scheduling backups with cron: $BACKUP_CRON"

# Write crontab
echo "$BACKUP_CRON /bin/sh -c '. /opt/backup/backup.sh' >> /proc/1/fd/1 2>&1" | crontab -

# Run crond in foreground
crond -f -l 2
