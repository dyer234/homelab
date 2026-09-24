# openclaw

[OpenClaw](https://docs.openclaw.ai) gateway: a personal assistant on
messaging channels (WhatsApp first), using the ContextForge MCP gateway
([../mcp](../mcp/)) for tools. Two agents, one per virtual server:

| Agent | MCP server | Answers | Tools |
|---|---|---|---|
| `media` (default) | `media` | WhatsApp DMs | Sonarr, Radarr, Prowlarr, Bazarr, Emby, VPN status |
| `ops` | `ops` | a WhatsApp group you bind | Docker, Jenkins, VPN status; owns every non-media container |

Each agent is denied the other's server (`mcp:<server>:*` in `tools.deny`),
and `media` has no shell/file/browser tools at all.

## Locked down

No Docker socket, no host network, every capability dropped,
`no-new-privileges`. The container can reach its own directories below,
`contextforge:4444` and the internet; it cannot run anything on the host.
The media agent additionally has no exec/write/browser tools.

- `openclaw.json5` — committed seed. `make init` copies it to
  `state/openclaw.json` once; OpenClaw owns the live file after that
  (channel logins, plugin installs and the Control UI write to it).
- `workspaces/<agent>/AGENTS.md` — personas, mounted as each agent's
  workspace; edit in place, picked up by the next session.
- `state/` — everything OpenClaw writes: live config, WhatsApp session,
  per-agent SQLite, installed plugins. Gitignored, backed up by `backups/`.
- `auth-secrets/` — provider auth profiles (gitignored).

## First start

1. Add to the 1Password `homelab` item: `openclaw_gateway_token`
   (`openssl rand -hex 32`) and `openai_api_key` (the key Open WebUI uses).
2. `make init && make up`
3. Connect channels yourself, from inside the container:
   `make cli ARGS="channels login"`. For WhatsApp that installs
   `@openclaw/whatsapp` into `state/` (the upstream image bundles only
   `codex` + `diagnostics-otel`) and shows a QR code. Nothing about channel
   setup is automated here; the Control UI at `https://openclaw.<DOMAIN>`
   (paste the gateway token) does the same job.

Because `state/` is a bind mount, an installed channel plugin and its session
survive restarts, rebuilds and image pulls — there is nothing to reinstall at
build time.

## Routing the groups

Two WhatsApp groups carry the traffic — **tv** to the Media Manager, **ops**
to Ops. The WhatsApp channel cannot look a group up by name, so its JID has to
be learned from a message it delivered. Create both groups with the linked
number in them, add whoever should have access, then:

```
make groups-open            # admit every group, temporarily (DMs stay off)
make restart
# send one message in the tv group and one in the ops group
make groups-seen            # prints the JIDs that arrived
make groups TV_JID=120363...@g.us OPS_JID=120363...@g.us
make restart
```

The last step is the final posture: `groupPolicy: "open"` (every member of an
admitted group may talk to the bot, no per-number allowlist), a `groups` map
holding only those two JIDs with `requireMention: false` (the bot answers
every message, not only @-mentions, and no other group is admitted), and the
two peer bindings. Copy both JIDs into `openclaw.json5` so a rebuilt `state/`
comes up the same.

**The number is public**, so there is no catch-all binding and DMs are
disabled: a message from outside those two groups reaches no agent at all.
Group membership is the access control, and only you can add people. To let
specific numbers DM the bot as well:

```
DM_ALLOW="+34600000000" make groups TV_JID=... OPS_JID=...
```

## Day to day

- `make cli ARGS="…"` — any `openclaw` command against the running gateway
  (`channels status`, `models set openai/gpt-6-astra`, `config get agents`,
  `mcp list`, `pairing list`).
- `make doctor` — self-check; `make logs` — gateway log; `make shell` — a
  shell in the container.
- Model: `agents.defaults.model` in the seed (`openai/gpt-5.6`). Change live
  with `make cli ARGS="models set <id>"`.

## Migration

`make down` here, `rsync` this directory (including `state/`) to the Linux
server, `make up` there. Only one gateway may hold the WhatsApp session at a
time.
