#!/usr/bin/env python3
"""Tiny JSON endpoint listing the Jenkins build agents and their state, for
the CI Agents card on the Homepage dashboard.

Asks the controller over the Docker network with the admin API token (the
same one infra/ci-agent uses to create the nodes). Served on :8080 as a list
Homepage's customapi `dynamic-list` display can render directly, offline
agents first so trouble is at the top:

    [{"name": "cloud-agent-amd64-1", "status": "Online · Idle"},
     {"name": "cloud-agent-amd64-2", "status": "Offline"}]

Standard library only, so it runs on a stock python:alpine image.
"""

import base64
import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

JENKINS_URL = os.environ.get("JENKINS_URL", "http://jenkins:8080").rstrip("/")
USER = os.environ["JENKINS_API_USER"]
TOKEN = os.environ["JENKINS_API_TOKEN"]
PORT = int(os.environ.get("PORT", "8080"))


def agents():
    req = urllib.request.Request(
        JENKINS_URL + "/computer/api/json?tree=computer[displayName,offline,idle,temporarilyOffline]")
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{USER}:{TOKEN}".encode()).decode())
    with urllib.request.urlopen(req, timeout=10) as resp:
        computers = json.load(resp)["computer"]
    rows = []
    for c in computers:
        if c["displayName"] == "Built-In Node":  # the controller itself, not an agent
            continue
        if c["temporarilyOffline"]:
            state = "Offline · marked by admin"
        elif c["offline"]:
            state = "Offline"
        else:
            state = "Online · Idle" if c["idle"] else "Online · Busy"
        rows.append({"name": c["displayName"], "online": not c["offline"], "status": state})
    rows.sort(key=lambda r: (r["online"], r["name"]))
    return rows or [{"name": "no agents", "status": ""}]


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body = json.dumps(agents()).encode()
            status = 200
        except Exception as e:  # noqa: BLE001 - surface anything on the card
            body = json.dumps([{"name": "error", "status": str(e)}]).encode()
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
