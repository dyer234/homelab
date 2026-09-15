# home-traefik

Reverse proxy for all homelab services using [Traefik](https://traefik.io/).

## What it does

- Routes traffic to services based on `Host()` rules defined in each service's Docker labels
- Terminates TLS with Let's Encrypt certificates via DNS-01 challenge through DigitalOcean
- Redirects all HTTP to HTTPS
- Exposes the Traefik dashboard at `https://<DOMAIN>/traefik`

## Network

Creates the `traefik-public` Docker network. All other services join this network to be routable.

## Configuration

Variables and where they are set:

| Variable | Description |
|---|---|
| `ACME_EMAIL` | Email for Let's Encrypt registration (`1pass.env`) |
| `DOMAIN` | Root domain (`../homelab.env`) |
| `DO_AUTH_TOKEN` | DigitalOcean API token for DNS-01 challenge (`1pass.env` → 1Password `do_token`) |

## Compose files

- `docker-compose.yml` — Full setup with Let's Encrypt ACME
- `docker-compose.no-acme.yml` — Local/dev override without ACME (self-signed TLS)

Set `NO_ACME=true` in `../homelab.local.env` to use the local override (`scripts/up.sh` and `make` both read it).

## Data

- `letsencrypt/acme.json` — Certificate store (backed up via the `backups` service)
