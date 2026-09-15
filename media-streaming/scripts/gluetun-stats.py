#!/usr/bin/env python3
"""Tiny JSON endpoint for the Homepage "VPN (Gluetun)" card.

Gluetun's control server can say whether the tunnel is up *right now*, but it
has no memory: a tunnel that flaps every 11 seconds looks identical to one
that has been solid for a week. The failure this exists for (Docker Desktop
silently dropping outbound UDP, Sept 2026) showed up as exactly that — 8,000+
"restarting VPN" cycles while qBittorrent sat on "Downloading metadata".

So this reads gluetun's own log through the Docker socket and counts those
restart lines. Served on :8080 as e.g.

    {"restarts_1h": 0, "restarts_24h": 3, "last_restart": "2h 14m ago"}

Counts come from the current container's log, so they reset to zero whenever
gluetun is recreated (not merely restarted).

Standard library only, so it runs on a stock python:alpine image. Read-only
socket mount; it only ever calls GET /containers/<name>/{json,logs}.
"""

import http.client
import json
import os
import socket
import struct
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

CONTAINER = os.environ.get("GLUETUN_CONTAINER", "gluetun")
DOCKER_SOCKET = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")
PORT = int(os.environ.get("PORT", "8080"))
# The line gluetun logs every time the tunnel fails its healthcheck and it
# tears the VPN down to try another server.
RESTART_MARKER = "restarting VPN"


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost")
        self.unix_path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(10)
        self.sock.connect(self.unix_path)


def docker_get(path):
    conn = UnixHTTPConnection(DOCKER_SOCKET)
    conn.request("GET", path)
    resp = conn.getresponse()
    body = resp.read()
    conn.close()
    if resp.status != 200:
        raise RuntimeError(f"docker {path} -> {resp.status}: {body[:200]!r}")
    return body


def demux(raw):
    """Docker multiplexes stdout/stderr of non-TTY containers as
    8-byte header (stream, 0, 0, 0, len[4]) + payload frames."""
    out = []
    i = 0
    while i + 8 <= len(raw):
        (size,) = struct.unpack(">I", raw[i + 4 : i + 8])
        out.append(raw[i + 8 : i + 8 + size])
        i += 8 + size
    return b"".join(out)


def read_log_lines(since):
    info = json.loads(docker_get(f"/containers/{CONTAINER}/json"))
    raw = docker_get(
        f"/containers/{CONTAINER}/logs?stdout=1&stderr=1&timestamps=1&since={since}"
    )
    if not info["Config"]["Tty"]:
        raw = demux(raw)
    return raw.decode("utf-8", "replace").splitlines()


def restart_times(lines):
    """Docker's own timestamps (first token, RFC3339 UTC) — independent of
    whatever TZ gluetun prints in its own log prefix."""
    times = []
    for line in lines:
        if RESTART_MARKER not in line:
            continue
        stamp = line.split(" ", 1)[0]
        try:
            # Nanosecond precision; datetime only parses to microseconds.
            times.append(
                datetime.fromisoformat(stamp[:26] + "+00:00")
                if len(stamp) > 27
                else datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            )
        except ValueError:
            continue
    return times


def humanize(delta_s):
    m = int(delta_s // 60)
    if m < 1:
        return "just now"
    h, m = divmod(m, 60)
    return f"{h}h {m}m ago" if h else f"{m}m ago"


def stats():
    now = datetime.now(timezone.utc)
    since = int(time.time()) - 24 * 3600
    times = restart_times(read_log_lines(since))
    last = max(times) if times else None
    return {
        "restarts_1h": sum(1 for t in times if (now - t).total_seconds() <= 3600),
        "restarts_24h": len(times),
        "last_restart": humanize((now - last).total_seconds()) if last else "none in 24h",
    }


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body = json.dumps(stats()).encode()
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
