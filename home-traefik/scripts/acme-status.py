#!/usr/bin/env python3
"""Tiny JSON endpoint listing every certificate Traefik holds and when it
expires, for the Let's Encrypt card on the Homepage dashboard.

Reads the ACME stores Traefik writes (acme.json, plus acme-staging.json when
staging has been used) straight off the shared read-only mount, so no API and
no secret are involved. Served on :8080 as a list Homepage's customapi
`dynamic-list` display can render directly, soonest expiry first:

    [{"name": "*.dyerwolf.xyz", "status": "89d · Dec 14"},
     {"name": "*.dyerwolf.xyz (staging)", "status": "Expired"}]

Standard library only, so it runs on a stock python:alpine image. The PEM is
decoded with ssl's private _test_decode_cert (the same routine behind
ssl.SSLSocket.getpeercert), which is the only x509 parser in the stdlib.
"""

import base64
import json
import os
import ssl
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

ACME_DIR = os.environ.get("ACME_DIR", "/letsencrypt")
PORT = int(os.environ.get("PORT", "8080"))
# Traefik renews at 30 days out; anything closer than that is worth a look.
WARN_DAYS = 30


def not_after(pem):
    with tempfile.NamedTemporaryFile("w", suffix=".pem", delete=False) as f:
        f.write(pem)
        path = f.name
    try:
        info = ssl._ssl._test_decode_cert(path)  # noqa: SLF001
    finally:
        os.unlink(path)
    return datetime.fromtimestamp(ssl.cert_time_to_seconds(info["notAfter"]), timezone.utc)


def certificates():
    rows = []
    for fname in sorted(os.listdir(ACME_DIR)):
        if not fname.endswith(".json"):
            continue
        staging = "staging" in fname
        with open(os.path.join(ACME_DIR, fname)) as f:
            store = json.load(f)
        for resolver in store.values():
            for cert in resolver.get("Certificates") or []:
                dom = cert["domain"]
                # Show the broadest name: the wildcard SAN when there is one.
                names = [dom["main"]] + list(dom.get("sans") or [])
                name = next((n for n in names if n.startswith("*.")), names[0])
                if staging:
                    name += " (staging)"
                try:
                    # Leaf certificate is first in Traefik's PEM bundle.
                    pem = base64.b64decode(cert["certificate"]).decode()
                    leaf = pem.split("-----END CERTIFICATE-----")[0] + "-----END CERTIFICATE-----\n"
                    expires = not_after(leaf)
                except Exception as e:  # noqa: BLE001
                    rows.append({"name": name, "days": -1, "status": f"unreadable: {e}"})
                    continue
                days = (expires - datetime.now(timezone.utc)).days
                if days < 0:
                    state = "Expired"
                elif days < WARN_DAYS:
                    state = f"Expiring · {days}d"
                else:
                    state = f"{days}d · {expires:%b %-d}"
                rows.append({"name": name, "expires": expires.isoformat(), "days": days, "status": state})
    rows.sort(key=lambda r: r["days"])
    return rows


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            body = json.dumps(certificates()).encode()
            status = 200
        except Exception as e:  # noqa: BLE001 - surface anything on the card
            body = json.dumps([{"name": "error", "status": str(e)}]).encode()
            status = 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # keep the container log quiet
        pass


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
