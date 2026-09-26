# n8n

Workflow automation at `https://n8n.<DOMAIN>`. Data in `data/` (gitignored,
backed up). Committed workflow definitions live in `workflows/` and are
mounted read-only at `/opt/workflows` for reference from inside the container;
n8n keeps its own copies once imported, so edit in the UI and export back here
when a workflow changes.

## arr download watch

Closes the loop between the OpenClaw media agent and the *arr apps, with no
LLM involved after the grab:

```
tv group -> media agent grabs a release
              └─ track-download tool -> POST /webhook/track-download
                                          └─ redis n8n:openclaw:dl:<app>:<id>  (TTL 48h)

Sonarr/Radarr webhook -> POST /webhook/arr-event
   ImportComplete/Download/Upgrade -> "Downloaded: ..."   -> WhatsApp, record cleared
   ManualInteractionRequired       -> "Import blocked: ..." -> WhatsApp, record cleared

every 20 min -> sweep n8n:openclaw:dl:* -> anything older than ARR_WATCH_STALE_HOURS
                                        -> "still not finished" -> record closed
```

The `redis: store pending` node asks for a 48h TTL, but this n8n's Redis node
declares `expire` twice (once for `incr`, once for `set`) and resolves the
wrong one, so the key is written without one - verified against the running
node. The 20-minute sweep is therefore the real cleaner: it closes any record
older than `ARR_WATCH_STALE_HOURS` after reporting it. The TTL is left in the
workflow so it starts working if the node is fixed upstream.

Replies are templated in Code nodes and posted through the OpenClaw gateway
(`POST http://openclaw:18789/tools/invoke`, the `message` tool) using
`OPENCLAW_GATEWAY_TOKEN` from the environment. Import messages go out as the
show's poster with the text as caption: the public TVDB/TMDB URL from the
webhook payload, fetched by OpenClaw (its SSRF guard refuses `sonarr:8989`).
The 18:00 digest sends one poster per show. Nothing here calls a model, and
the watchdog never calls Sonarr: completion *and* import-blocked both arrive
as webhooks, so the only case left to time out is silence.

### Setting it up

1. `make up` (picks up the token, the workflows mount and the env-access flag).
2. In the UI: **Credentials → New → Redis**, name it `homelab redis`,
   host `redis`, port `6379`, no password.
3. **Workflows → Import from File** → `workflows/arr-download-watch.json` from
   this repo (the picker runs in the browser, so use the host path, e.g.
   `~/projects/homelab/n8n/workflows/arr-download-watch.json`; ⌘⇧G pastes a
   path). Pick the credential on the four Redis nodes, **Activate**.
4. `make webhooks` — registers the Sonarr and Radarr connections. Must come
   after activation: both apps test the URL before saving.
5. `cd ../mcp && make register` — exposes the `track-download` tool to the
   media agent.

Redis keys are namespaced `n8n:openclaw:*` - n8n owns them on OpenClaw's
behalf, so the prefix says which service will clean them up.

### Checking it

- `docker exec redis redis-cli keys 'n8n:openclaw:dl:*'` — what is in flight.
- n8n → Executions — every webhook and sweep, with the payloads.
- Sonarr → Settings → Connect → *n8n download watch* → Test.
