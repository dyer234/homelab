# homelab

Docker-based homelab running media streaming services behind Traefik, with DNS managed via OpenTofu and backups to Backblaze B2.

## Apps

| App | Description |
|---|---|
| [home-traefik](home-traefik/) | Traefik reverse proxy with Let's Encrypt TLS |
| [media-streaming](media-streaming/) | Emby, Sonarr, Radarr, Prowlarr, Bazarr, qBittorrent over WireGuard |
| [homepage](homepage/) | Dashboard for all services |
| [backups](backups/) | Automated backups to Backblaze B2 |
| [infra](infra/) | DNS records via OpenTofu on DigitalOcean |

## Scripts

| Script | Description |
|---|---|
| `scripts/up.sh` | Start all apps |
| `scripts/down.sh` | Stop all apps |

## Setup

1. Configure DNS: `cd infra/dns && tofu apply`
2. Copy `.env.template` to `.env` in each app directory and fill in values
3. Copy `backups/rclone.conf.template` to `backups/rclone.conf` with B2 credentials
4. Start everything: `bash scripts/up.sh`

All services are exposed as `<service>.dyerwolf.xyz` subdomains, routed through Traefik.
