#!/usr/bin/env python3
"""Point Sonarr and Radarr at the arr-download-watch workflow (`make webhooks`).

Creates (or updates) a Webhook connection named "n8n download watch" in both
apps, firing on import, upgrade, and manual-interaction-required. Idempotent.

Both apps test the URL before saving, so the workflow must already be imported
AND ACTIVE in n8n, otherwise this fails with a 404 from the test post.

Runs inside a throwaway container on media_net: the *arr apps are not
reachable from the host by name. API keys are read from each app's own
config.xml, never copied anywhere.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

APPS = {"sonarr": 8989, "radarr": 7878}
NAME = "n8n download watch"
URL = os.environ.get("ARR_WEBHOOK_URL", "http://n8n:5678/webhook/arr-event")


def call(base: str, headers: dict, method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(errors="replace")[:500]


def main() -> int:
    rc = 0
    for app, port in APPS.items():
        key = os.environ.get(f"{app.upper()}_API_KEY")
        if not key:
            print(f"{app}: no {app.upper()}_API_KEY in env, skipped", file=sys.stderr)
            rc = 1
            continue
        base = f"http://{app}:{port}/api/v3"
        headers = {"X-Api-Key": key, "Content-Type": "application/json"}

        code, schema = call(base, headers, "GET", "/notification/schema")
        if code != 200:
            print(f"{app}: schema failed {code}: {schema}", file=sys.stderr)
            rc = 1
            continue
        hook = next(s for s in schema if s["implementation"] == "Webhook")

        body = dict(hook)
        body.update({
            "name": NAME,
            "implementation": "Webhook",
            "configContract": hook.get("configContract", "WebhookSettings"),
            # Import finished, an upgrade replaced a file, or the download will
            # not import without a human. Only onDownload for imports: Sonarr
            # v4's onImportComplete also posts eventType "Download" (with
            # episodeFiles, no episodeFile), so enabling both sends every
            # import twice and doubles the digest.
            "onGrab": False,
            "onDownload": True,
            "onUpgrade": True,
            "onImportComplete": False,
            "onManualInteractionRequired": True,
            "onRename": False,
            "onHealthIssue": False,
            "onApplicationUpdate": False,
            "includeHealthWarnings": False,
            "tags": [],
        })
        for f in body["fields"]:
            if f["name"] == "url":
                f["value"] = URL
            if f["name"] == "method":
                f["value"] = 1  # POST

        code, existing = call(base, headers, "GET", "/notification")
        match = [n for n in (existing or []) if n.get("name") == NAME] if code == 200 else []
        if match:
            body["id"] = match[0]["id"]
            code, res = call(base, headers, "PUT", f"/notification/{body['id']}", body)
            verb = "updated"
        else:
            code, res = call(base, headers, "POST", "/notification", body)
            verb = "created"

        if code in (200, 201, 202):
            print(f"{app}: {verb} '{NAME}' -> {URL}")
        else:
            print(f"{app}: FAILED {code}: {res}", file=sys.stderr)
            print(f"{app}: is the workflow imported and ACTIVE in n8n? both apps "
                  f"test the URL before saving.", file=sys.stderr)
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
