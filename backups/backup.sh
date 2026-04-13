#!/bin/sh
REMOTE="b2:${B2_BUCKET:-homelab-backups}"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

run_backup() {
  log "Starting backup"

  log "Backing up home-traefik/letsencrypt"
  rclone sync /data/home-traefik/letsencrypt "$REMOTE/home-traefik/letsencrypt" --verbose

  log "Backing up media-streaming/config"
  rclone sync /data/media-streaming/config "$REMOTE/media-streaming/config" --verbose

  log "Backing up n8n/data"
  rclone sync /data/n8n/data "$REMOTE/n8n/data" --filter-from /opt/backup/exclude-filters.txt --verbose

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
