# homepage

Dashboard using [Homepage](https://gethomepage.dev/) for an overview of all homelab services.

## What it does

- Provides a single dashboard at `dashboard.<DOMAIN>`
- Auto-discovers services via Docker labels (`homepage.*` labels on each service)
- Groups services into Media, Find New, and Downloads sections

## Configuration

Copy `.env.template` to `.env` and fill in:

| Variable | Description |
|---|---|
| `DOMAIN` | Root domain for Traefik routing |

Service tiles are configured via Docker labels on each service container, not in Homepage's config files directly. Layout is defined in `config/settings.yaml`.
