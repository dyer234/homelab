# dozzle

Live, streaming container logs in the browser at `logs.<DOMAIN>`, linked from
the dashboard's Infrastructure group.

## What it does

- Streams stdout/stderr of every container on the host (read-only Docker socket)
- Search/filter within a log, follow several containers side by side
- Stateless: no volume, nothing persisted

## Configuration

No secrets, so no `1pass.env`. `DOMAIN` and `TZ` come from `../homelab.env`.
Start with `make up` or `scripts/up.sh`.
