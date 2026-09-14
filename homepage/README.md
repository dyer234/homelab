# homepage

Dashboard using [Homepage](https://gethomepage.dev/) for an overview of all homelab services.

## What it does

- Provides a single dashboard at `dashboard.<DOMAIN>`
- Auto-discovers services via Docker labels (`homepage.*` labels on each service)
- Groups services into Media, Find New, and Downloads sections

## Configuration

Variables live in `1pass.env` (committed; secrets are `op://` references resolved by `op run`). Start with `make up` or `scripts/up.sh`.

| Variable | Description |
|---|---|
| `DOMAIN` | Root domain for Traefik routing |
| `JENKINS_API_USER` | Jenkins account the API token belongs to |
| `JENKINS_API_TOKEN` | 1Password reference to a Jenkins API token (user > Security > API Token) |

Service tiles for containers on this host are configured via Docker labels on each container. `config/services.yaml` holds static tiles for things that are not local containers — currently the DigitalOcean CI agent, whose status is read from Jenkins' node API. Layout is defined in `config/settings.yaml`.
