# homelab

Docker-based homelab running media streaming services behind Traefik, with DNS managed via OpenTofu and backups to Backblaze B2.

## Apps

| App | Description |
|---|---|
| [home-traefik](home-traefik/) | Traefik reverse proxy with Let's Encrypt TLS |
| [media-streaming](media-streaming/) | Emby, Sonarr, Radarr, Prowlarr, Bazarr, qBittorrent over WireGuard |
| [homepage](homepage/) | Dashboard for all services |
| [backups](backups/) | Automated backups to Backblaze B2 |
| [tailscale](tailscale/) | Tailnet subnet router putting the Docker network on the tailnet |
| [n8n](n8n/) | Workflow automation; watches *arr downloads and reports back through OpenClaw |
| [mcp](mcp/) | ContextForge MCP gateway aggregating every tool behind one endpoint |
| [openclaw](openclaw/) | WhatsApp assistant (OpenClaw) using the MCP gateway for tools |
| [infra](infra/) | DNS, tailnet policy and cloud CI agents via OpenTofu on DigitalOcean |

## Scripts

| Script | Description |
|---|---|
| `scripts/up.sh` | Start all apps |
| `scripts/down.sh` | Stop all apps |

## Setup

1. Configure DNS: `cd infra/dns && tofu apply`
2. Shared variables (`DOMAIN`, `TZ`, `PUID`/`PGID`, `MEDIA_*`, `WG_HOST`) live in
   `homelab.env`. On a host that differs from those defaults, copy
   `homelab.local.env.template` to `homelab.local.env` and adjust.
3. Sign in to 1Password CLI (`op signin`, or export `OP_SERVICE_ACCOUNT_TOKEN`
   on a server). Each app's config is its committed `1pass.env`: secrets as
   `op://projects/homelab/...` references, resolved by `op run` at start; the
   rest in the clear. No per-app `.env` is needed (one is honoured if present).
4. Copy `backups/rclone.conf.template` to `backups/rclone.conf` with B2 credentials
5. Start everything: `bash scripts/up.sh`

All services are exposed as `<service>.dyerwolf.xyz` subdomains, routed through Traefik.
