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

| Variable | Where | Description |
|---|---|---|
| `TZ`, `PUID`, `PGID`, `DOMAIN` | `../homelab.env` | Shared across the homelab |
| `MEDIA_HOST`, `MEDIA_CONTAINER` | `../homelab.env` | Host path to media files and its mount point in the containers |
| `EMBY_API_KEY` | `../homelab.local.env` | Emby API key for the Homepage widget; unique per Emby install, so set it once per host |
| `PROTONVPN_*`, `VPN_PORT_FORWARDING*`, `FIREWALL_VPN_INPUT_PORTS` | `1pass.env` | Gluetun config; the private key is an `op://` reference |

## Data

- `config/` — Per-service config directories (backed up via the `backups` service)
- `media/` — Media files (not backed up)
- `wireguard/` — WireGuard tunnel config and healthcheck script
