# media-streaming

Media acquisition and streaming stack, routed through Traefik.

## Services

| Service | Port | URL | Description |
|---|---|---|---|
| Emby | 8096 | `emby.<DOMAIN>` | Media server |
| Sonarr | 8989 | `sonarr.<DOMAIN>` | TV show management |
| Radarr | 7878 | `radarr.<DOMAIN>` | Movie management |
| Prowlarr | 9696 | `prowlarr.<DOMAIN>` | Indexer manager |
| Bazarr | 6767 | `bazarr.<DOMAIN>` | Subtitle management |
| qBittorrent | 8181 | `qbit.<DOMAIN>` | Torrent client (routed through WireGuard) |
| WireGuard | — | — | VPN tunnel for qBittorrent |
| Autoheal | — | — | Restarts unhealthy containers |

## Network

qBittorrent runs inside WireGuard's network stack (`network_mode: service:wireguard`). Traefik labels for qBittorrent are on the WireGuard container. Autoheal monitors both and restarts them if the WireGuard tunnel drops.

## Configuration

Copy `.env.template` to `.env` and fill in:

| Variable | Description |
|---|---|
| `TZ` | Timezone (e.g. `America/Los_Angeles`) |
| `MEDIA_HOST` | Host path to media files |
| `MEDIA_CONTAINER` | Container mount point for media |
| `DOMAIN` | Root domain for Traefik routing |
| `EMBY_API_KEY` | Emby API key (for Homepage widget) |

## Data

- `config/` — Per-service config directories (backed up via the `backups` service)
- `media/` — Media files (not backed up)
- `wireguard/` — WireGuard tunnel config and healthcheck script
