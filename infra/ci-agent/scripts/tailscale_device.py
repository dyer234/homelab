#!/usr/bin/env python3
"""Delete tailnet device records for build agents, for OpenTofu.

A droplet REGISTERS ITSELF with the tailnet from cloud-init, so the device
record is not a resource tofu ever creates and cannot be one it tracks. But
destroying the droplet leaves that record behind as an offline node, and those
accumulate against the free plan's device limit -- one per rebuild, forever.

The alternative is an ephemeral auth key, where the coordination server removes
the node a few minutes after it disconnects. That is deliberately NOT what this
fleet uses: these are persistent agents that must survive a reboot or a network
blip without being garbage-collected mid-build. So the cleanup is explicit, and
it hangs off a destroy-time provisioner in main.tf.

    tailscale_device.py delete <hostname>   idempotent; removes EVERY device
                                            whose hostname matches, which also
                                            clears records orphaned by earlier
                                            rebuilds
    tailscale_device.py list [prefix]       hostname / id / last-seen, to see
                                            what is actually registered

Credentials come from the environment, which `op run --env-file=1pass.env`
populates -- the same OAuth client that mints the auth key in main.tf, which
needs BOTH scopes:

    auth_keys       write   to mint the registration key
    devices:core    write   to delete a device (read alone gives 403 here)

    TF_VAR_tailscale_oauth_client_id
    TF_VAR_tailscale_oauth_client_secret

Standard library only, matching jenkins_node.py.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.tailscale.com/api/v2"
CLIENT_ID = os.environ.get("TF_VAR_tailscale_oauth_client_id", "")
CLIENT_SECRET = os.environ.get("TF_VAR_tailscale_oauth_client_secret", "")

# "-" means "the tailnet the authenticated identity belongs to", which saves
# hardcoding the org name and keeps this working if the tailnet is renamed.
TAILNET = "-"


def die(msg):
    print(f"tailscale_device.py: {msg}", file=sys.stderr)
    sys.exit(1)


def token():
    """Exchange the long-lived OAuth client for a short-lived access token.

    The client secret itself is never sent as a bearer token; it buys a token
    that expires in an hour. That is the whole reason this fleet uses an OAuth
    client rather than a stored API key -- the stored credential does not expire
    and the wire credential does not persist.
    """
    if not (CLIENT_ID and CLIENT_SECRET):
        die("need TF_VAR_tailscale_oauth_client_id and TF_VAR_tailscale_oauth_client_secret "
            "in the environment (run via make, under `op run`)")
    body = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "client_credentials",
    }).encode()
    req = urllib.request.Request(f"{API}/oauth/token", data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["access_token"]
    except urllib.error.HTTPError as e:
        die(f"oauth/token -> HTTP {e.code}: {e.read().decode()[:300]}")
    except urllib.error.URLError as e:
        die(f"oauth/token -> {e.reason}")


def call(method, path, tok, ok=(200,)):
    req = urllib.request.Request(API + path, method=method)
    req.add_header("Authorization", "Bearer " + tok)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        if e.code in ok:
            return e.code, e.read().decode()
        die(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:300]}")
    except urllib.error.URLError as e:
        die(f"{method} {path} -> {e.reason}")


def devices(tok, prefix=None):
    """Registered devices, as (hostname, id, last-seen) triples.

    Matching is on `hostname`, which is what cloud-init passes to
    `tailscale up --hostname=`, NOT on `name`. `name` is the MagicDNS FQDN and
    the coordination server DEDUPLICATES it -- a rebuilt agent whose old record
    still exists comes back as `cloud-agent-amd64-1-1`, so matching on it would
    silently skip exactly the stale records this is meant to remove.
    """
    _, body = call("GET", f"/tailnet/{TAILNET}/devices", tok)
    out = []
    for d in json.loads(body).get("devices", []):
        host = d.get("hostname", "")
        if prefix and not host.startswith(prefix):
            continue
        # lastSeen rather than a synthesised online/offline: the API has no
        # "online" field, and an agent that is merely idle looks identical to
        # one whose droplet is gone. The timestamp says which.
        out.append((host, d["id"], d.get("lastSeen", "never")))
    return out


def delete(hostname):
    tok = token()
    matches = [(h, i) for h, i, _ in devices(tok) if h == hostname]
    if not matches:
        print(f"device {hostname}: no tailnet record (already gone)")
        return
    if len(matches) > 1:
        # Normal for a rebuilt agent: the old record lingers holding the name
        # and clearing it is the point. NOT normal otherwise -- every stack
        # shares tag:ci-agent, so the hostname is the only thing separating
        # fleets, and a second stack left at the same agent_name_prefix puts
        # its LIVE agent in this list. Loud, because the victim just goes
        # quiet with no error of its own.
        print(f"tailscale_device.py: WARNING - {len(matches)} records share the "
              f"hostname {hostname}; deleting all of them. Expected after a "
              f"rebuild. If another stack uses this agent_name_prefix, one of "
              f"these is its running agent (see variables.tf).", file=sys.stderr)
    for host, dev_id in matches:
        # 200 on success. 404 means someone removed it between the list and
        # here, which is success for our purposes.
        call("DELETE", f"/device/{dev_id}", tok, ok=(200, 404))
        print(f"device {host} ({dev_id}): deleted")


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "delete" and len(argv) == 3:
        delete(argv[2])
    elif cmd == "list":
        for row in devices(token(), argv[2] if len(argv) > 2 else None):
            print("%-24s %-20s %s" % row)
    else:
        die(__doc__)


if __name__ == "__main__":
    main(sys.argv)
