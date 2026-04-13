# backups

Automated backups to Backblaze B2 using [rclone](https://rclone.org/).

## What it backs up

| Source | Remote path |
|---|---|
| `home-traefik/letsencrypt/` | `<bucket>/home-traefik/letsencrypt/` |
| `media-streaming/config/` | `<bucket>/media-streaming/config/` |

## How it works

- Runs a backup immediately on container startup
- Then repeats on a configurable interval (default: 24 hours)
- Uses `rclone sync` to mirror local state to B2

## Configuration

Copy `.env.template` to `.env` and `rclone.conf.template` to `rclone.conf`, then fill in:

### .env

| Variable | Description |
|---|---|
| `TZ` | Timezone |
| `BACKUP_INTERVAL` | Seconds between backups (default: `86400`) |
| `B2_BUCKET` | Backblaze B2 bucket name |

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
