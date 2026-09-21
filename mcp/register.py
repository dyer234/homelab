#!/usr/bin/env python3
"""Sync the gateway's registrations from catalog/ (idempotent; `make register`).

Stdlib only, runs on the host. Three passes, each upsert-by-name:

  gateways  every stdio server in stdio/servers.json is registered as an
            upstream MCP server at http://mcp-stdio:8096/servers/<name>/mcp;
            the gateway discovers its tools, named <server>-<tool>.
  tools     every catalog/<app>.json is a set of REST tools against one
            service. The API key is read at run time from the service's own
            config (the *arr config.xml, Bazarr's config.yaml, EMBY_API_KEY
            from homelab*.env) and stored encrypted in the gateway DB; it is
            never written to disk here.
  servers   catalog/servers.json defines virtual servers: name -> tool-name
            globs. Each gets a UUID derived from its name, so the client URL
            https://mcp.<DOMAIN>/servers/<id>/mcp is stable across reprovisions.

Catalog tool fields: name, description, method, path (relative to base_url;
{param} placeholders are filled from arguments, remaining arguments become
query params on GET/DELETE and the JSON body otherwise), input (JSON-schema
properties), required, readOnly, destructive, filter (jq program that trims
the upstream response before it reaches the model).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import ssl
import sys
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CATALOG = HERE / "catalog"
STDIO_URL = "http://mcp-stdio:8096/servers/{name}/mcp"


# --- env / secrets -----------------------------------------------------------

def env_files() -> dict[str, str]:
    """KEY=value pairs from homelab.env then homelab.local.env (later wins)."""
    out: dict[str, str] = {}
    for f in (ROOT / "homelab.env", ROOT / "homelab.local.env"):
        if f.exists():
            for line in f.read_text().splitlines():
                m = re.match(r"^\s*([A-Z0-9_]+)=(.*)$", line)
                if m:
                    out[m.group(1)] = m.group(2).strip()
    return out


ENV = {**env_files(), **os.environ}


def api_key(spec: dict | None) -> str | None:
    if not spec:
        return None
    if "xml" in spec:
        tree = ET.parse(ROOT / "mcp" / spec["xml"])
        return tree.getroot().findtext("ApiKey")
    if "yaml_apikey" in spec:
        text = (ROOT / "mcp" / spec["yaml_apikey"]).read_text()
        m = re.search(r"^\s*apikey:\s*['\"]?([A-Za-z0-9]+)", text, re.M)
        return m.group(1) if m else None
    if "env" in spec:
        return ENV.get(spec["env"]) or None
    raise ValueError(f"unknown api_key spec {spec}")


# --- gateway client ----------------------------------------------------------

class Gateway:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.ctx = ssl.create_default_context()
        if ENV.get("NO_ACME") == "true":  # self-signed via Traefik on the Mac
            self.ctx.check_hostname = False
            self.ctx.verify_mode = ssl.CERT_NONE

    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=120) as r:
                raw = r.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:600]
            sys.exit(f"{method} {path} -> {e.code}: {detail}")

    def by_name(self, path: str) -> dict[str, dict]:
        # list endpoints page at 50 by default; limit=0 means everything
        path += ("&" if "?" in path else "?") + "limit=0"
        items = self.call("GET", path) or []
        return {i["name"]: i for i in items}


# --- passes ------------------------------------------------------------------

def sync_gateways(gw: Gateway) -> None:
    existing = gw.by_name("/gateways?include_inactive=true")
    servers = json.loads((HERE / "stdio" / "servers.json").read_text())["mcpServers"]
    for name, spec in servers.items():
        if spec.get("enabled", True) is False:
            continue
        if name in existing:
            print(f"gateway  {name:<28} ok")
            continue
        body = {"name": name, "url": STDIO_URL.format(name=name), "transport": "STREAMABLEHTTP",
                "description": f"stdio sidecar: {spec['command']} {' '.join(spec.get('args', []))}"}
        r = gw.call("POST", "/gateways", body)
        print(f"gateway  {name:<28} created  reachable={r.get('reachable')}")


def tool_payload(app: dict, t: dict, key: str | None) -> dict:
    props = t.get("input", {})
    method = t["method"].upper()
    body = {
        "name": t["name"],
        "description": t["description"],
        "integration_type": "REST",
        "request_type": method,
        "url": app["base_url"].rstrip("/") + t["path"],
        "input_schema": {"type": "object", "properties": props, "required": t.get("required", [])},
        "annotations": {
            "title": t["name"],
            "readOnlyHint": bool(t.get("readOnly", False)),
            "destructiveHint": bool(t.get("destructive", False)),
            "idempotentHint": method in ("GET", "PUT", "DELETE"),
            "openWorldHint": False,
        },
        "tags": app.get("tags", []),
        "visibility": "public",
        # jq program applied to the upstream response (field name is historical)
        "jsonpath_filter": t.get("filter", ""),
    }
    if key and app.get("auth_header"):
        # top-level fields; the schema's assemble_auth validator builds the
        # encrypted `auth` value from them (a nested `auth` dict is ignored)
        body["auth_type"] = "authheaders"
        body["auth_headers"] = [{"key": app["auth_header"], "value": key}]
    return body


def sync_tools(gw: Gateway) -> None:
    existing = gw.by_name("/tools?include_inactive=true")
    for f in sorted(CATALOG.glob("*.json")):
        if f.name == "servers.json":
            continue
        app = json.loads(f.read_text())
        key = api_key(app.get("api_key"))
        if app.get("api_key") and not key:
            print(f"tools    {f.stem:<28} SKIPPED: no API key found via {app['api_key']}")
            continue
        for t in app["tools"]:
            body = tool_payload(app, t, key)
            if t["name"] in existing:
                gw.call("PUT", f"/tools/{existing[t['name']]['id']}", body)
                print(f"tool     {t['name']:<28} updated")
            else:
                # POST routes take extra Body() params, so the model is enveloped
                gw.call("POST", "/tools", {"tool": body})
                print(f"tool     {t['name']:<28} created")


def sync_servers(gw: Gateway) -> None:
    tools = gw.by_name("/tools")
    wanted = json.loads((CATALOG / "servers.json").read_text())
    existing = gw.by_name("/servers?include_inactive=true")
    for name, spec in wanted.items():
        sid = uuid.uuid5(uuid.NAMESPACE_URL, f"homelab-mcp/servers/{name}").hex
        ids = sorted({tools[n]["id"] for n in tools for pat in spec["tools"] if fnmatch.fnmatch(n, pat)})
        body = {"name": name, "description": spec.get("description", ""), "associated_tools": ids, "visibility": "public"}
        cur = existing.get(name)
        if cur and cur["id"] != sid:
            # created by hand (random id) - replace so the URL becomes stable
            gw.call("DELETE", f"/servers/{cur['id']}")
            cur = None
        if cur:
            gw.call("PUT", f"/servers/{sid}", body)
            verb = "updated"
        else:
            gw.call("POST", "/servers", {"server": {"id": sid, **body}})
            verb = "created"
        print(f"server   {name:<28} {verb}  {len(ids):>3} tools  {gw.base}/servers/{sid}/mcp")


def main() -> None:
    base = os.environ.get("MCP_URL") or f"https://mcp.{ENV['DOMAIN']}"
    gw = Gateway(base)
    sync_gateways(gw)
    sync_tools(gw)
    sync_servers(gw)


if __name__ == "__main__":
    main()
