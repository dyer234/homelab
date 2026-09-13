# backups

Automated backups to Backblaze B2 using [rclone](https://rclone.org/).

## What it backs up

| Source | Remote path |
|---|---|
| `home-traefik/letsencrypt/` | `<bucket>/home-traefik/home-traefik-<date>.tar.gz` |
| `media-streaming/config/` | `<bucket>/media-streaming/media-streaming-<date>.tar.gz` |
| `n8n/data/` | `<bucket>/n8n/n8n-<date>.tar.gz` |
| `ai/open-webui/` | `<bucket>/ai/ai-<date>.tar.gz` |
| `navidrome/config/` | `<bucket>/navidrome/navidrome-<date>.tar.gz` |
| `jenkins/data/` | `<bucket>/jenkins/jenkins-<date>.tar.gz` |
| `gluetun/.env` | `<bucket>/gluetun-env/gluetun-env-<date>.tar.gz` |

Paths matching `exclude-filters.txt` (logs, caches, artwork, sqlite WAL files) are skipped.

## How it works

- Runs a backup immediately on container startup
- Then runs on `BACKUP_CRON` (default: daily at 3am)
- Each source is tarred and uploaded as a dated archive; archives older than
  `BACKUP_RETENTION_DAYS` are hard-deleted from the bucket

## Checking it worked

```bash
docker logs backups | grep -E 'ERROR|NOTICE|Backing up|complete'
docker exec backups rclone lsl b2:$B2_BUCKET
```

A healthy run has no `ERROR` lines and one dated archive per source.

## Configuration

Copy `.env.template` to `.env` and `rclone.conf.template` to `rclone.conf`, then fill in:

### .env

| Variable | Description |
|---|---|
| `TZ` | Timezone |
| `BACKUP_CRON` | Cron schedule (default: `0 3 * * *`) |
| `B2_BUCKET` | Backblaze B2 bucket name (required; must already exist) |
| `BACKUP_RETENTION_DAYS` | Days to keep archives (default: `7`) |

### rclone.conf

| Field | Description |
|---|---|
| `account` | Backblaze B2 Key ID |
| `key` | Backblaze B2 Application Key |

## Restoring

Run the restore script from the repo root:

```bash
bash backups/restore.sh
```

This pulls data from B2 back into the local directories. It will prompt for confirmation before overwriting.
