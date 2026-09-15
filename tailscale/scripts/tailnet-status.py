#!/usr/bin/env python3
"""Tiny JSON endpoint listing every other machine on the tailnet and whether
it is online, for the Tailscale card on the Homepage dashboard.

Asks tailscaled's LocalAPI over the unix socket the tailscale container shares
with us (GET /localapi/v0/status — the same call `tailscale status --json`
makes). The node already knows its peers' online state, so this needs no
Tailscale API key and no secret on the Homepage side.

Served on :8080 as a list Homepage's customapi `dynamic-list` display can
render directly, online machines first:

    [{"name": "gl-be3600", "status": "Online"},
     {"name": "daniel-s-mac-mini", "status": "Offline · 1d ago"}]

Standard library only, so it runs on a stock python:alpine image.
"""

import http.client
import json
import os
import socket
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

TS_SOCKET = os.environ.get("TS_SOCKET", "/var/run/tailscale/tailscaled.sock")
PORT = int(os.environ.get("PORT", "8080"))


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("local-tailscaled.sock")
        self.unix_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect(self.unix_path)


def tailscale_status():
    conn = UnixHTTPConnection(TS_SOCKET)
    conn.request("GET", "/localapi/v0/status")
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    if resp.status != 200:
        raise RuntimeError(f"localapi status -> {resp.status}: {body[:200]!r}")
    return json.loads(body)


def ago(stamp):
    """LastSeen is RFC3339; tailscaled reports year 0001 for 'unknown'."""
    if not stamp or stamp.startswith("0001-"):
        return None
    try:
        seen = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    s = (datetime.now(timezone.utc) - seen).total_seconds()
    if s < 3600:
        return f"{int(s // 60)}m ago"
    if s < 86400:
        return f"{int(s // 3600)}h ago"
    return f"{int(s // 86400)}d ago"


def machines():
    status = tailscale_status()
    rows = []
    for peer in (status.get("Peer") or {}).values():
        # DNSName is unique on the tailnet; HostName is not (two GL-BE3600s).
        name = (peer.get("DNSName") or peer.get("HostName") or "?").split(".")[0]
        online = bool(peer.get("Online"))
        if online:
            state = "Online"
        else:
            seen = ago(peer.get("LastSeen"))
            state = f"Offline · {seen}" if seen else "Offline"
        rows.append({"name": name, "os": peer.get("OS", ""), "online": online, "status": state})
    rows.sort(key=lambda r: (not r["online"], r["name"]))
    return rows


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body = json.dumps(machines()).encode()
            status = 200
        except Exception as e:  # noqa: BLE001 - surface anything on the card
            body = json.dumps({"error": str(e)}).encode()
            status = 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):  # keep container logs quiet
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
