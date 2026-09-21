# mcp

One MCP endpoint for every AI client (Claude Code, Open WebUI, n8n) instead of
wiring each tool into each client. [ContextForge](https://github.com/IBM/mcp-context-forge)
is the gateway; a small sidecar runs stdio-only servers for it.

```
client ──https://mcp.<DOMAIN>/servers/<id>/mcp──▶ contextforge ──┬─▶ mcp-stdio ──▶ uvx mcp-server-fetch
                                                    (SQLite)     │              └─▶ uvx mcp-server-time
                                                                 ├─▶ http://sonarr:8989   (REST wrapped as tools)
                                                                 └─▶ https://…/mcp        (remote MCP servers)
```

## First start

1. Add three fields to the `homelab` item in the `projects` vault (names in
   `1pass.env`): two `openssl rand -hex 32` values and an admin password.
2. `make up` — builds the sidecar image, pulls the gateway.
3. Open `https://mcp.<DOMAIN>/admin`, log in as `PLATFORM_ADMIN_EMAIL`.

## Registering tools

In the admin UI:

- **Gateways → Add**: an upstream MCP server. Sidecar servers are at
  `http://mcp-stdio:8096/servers/<name>/mcp` (Streamable HTTP); the names are
  the keys in `stdio/servers.json`. Remote servers are their public URL.
- **Tools → Add**: a REST endpoint wrapped as a single tool (Sonarr/Radarr/
  qBittorrent are reachable by container name on `media_net`). API keys are
  encrypted at rest with `AUTH_ENCRYPTION_SECRET`.
- **Virtual Servers → Add**: pick the tools one client should see. Each
  virtual server gets an ID; the client URL is
  `https://mcp.<DOMAIN>/servers/<id>/mcp`.

Auth is off for API and MCP callers (`AUTH_REQUIRED=false`: single user,
LAN-only host), so clients need only the URL. The admin UI still has a login
page; that is the only place the admin password is used. `make token` mints a
bearer token should auth ever be turned back on.

Claude Code, for example:

```
claude mcp add --transport http homelab https://mcp.<DOMAIN>/servers/<id>/mcp
```

## Adding a stdio server

Only PyPI packages: the sidecar has `uvx` but no `npx`. Add an entry to
`stdio/servers.json` in the usual `command`/`args`/`env` shape, `make restart`,
then register `http://mcp-stdio:8096/servers/<name>/mcp` as a gateway.
`make servers` shows what the sidecar is running.

## Data

`data/mcp.db` (gitignored, backed up by `backups/`) holds every registration,
virtual server and the admin account. Reprovision (new admin password, clean
slate): `make down`, delete `data/mcp.db`, `make up` — the admin is only
seeded when the DB is created, so a password change in 1Password alone does
nothing. `AUTH_ENCRYPTION_SECRET` must travel with the DB: a restored copy
under a different secret cannot decrypt stored upstream credentials. The
sidecar's `uv-cache` volume is disposable.
