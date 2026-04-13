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

Copy `.env.template` to `.env` and fill in:

| Variable | Description |
|---|---|
| `ACME_EMAIL` | Email for Let's Encrypt registration |
| `DOMAIN` | Root domain (e.g. `dyerwolf.xyz`) |
| `DO_AUTH_TOKEN` | DigitalOcean API token for DNS-01 challenge |

## Compose files

- `docker-compose.yml` — Full setup with Let's Encrypt ACME
- `docker-compose.no-acme.yml` — Local/dev override without ACME (self-signed TLS)

Set `COMPOSE_FILE=docker-compose.yml:docker-compose.no-acme.yml` in `.env` to use the local override.

## Data

- `letsencrypt/acme.json` — Certificate store (backed up via the `backups` service)
