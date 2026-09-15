#!/usr/bin/env python3
"""Manage Jenkins inbound (JNLP) agent nodes over the REST API, for OpenTofu.

Called from main.tf so that a Jenkins node is CREATED with each droplet, its
secret is read back rather than pasted into 1Password, and the node is DELETED
when the droplet is destroyed. Standard library only.

    jenkins_node.py ensure <name> <labels> <executors>   create if missing, else
                                                         update labels/executors
    jenkins_node.py secret                               tofu `external` data
                                                         source: reads {"name"}
                                                         from stdin, prints
                                                         {"secret": ...}
    jenkins_node.py delete <name>                        idempotent
    jenkins_node.py list [label]                         name / online / idle

Credentials come from the environment, which `op run --env-file=1pass.env`
populates. They are deliberately NOT tofu variables: everything a data source
is given ends up in terraform.tfstate, and an admin API token has no business
there. The droplet's own JNLP secret does land in state (inside user_data), but
that only grants "be this one agent" and dies with the node.

    DOMAIN                     root domain; Jenkins is https://jenkins.$DOMAIN
                               (exported by common-tofu.mk from homelab.env)
    TF_VAR_jenkins_admin_url   optional override of that URL
    TF_VAR_jenkins_api_user    the account the token belongs to
    TF_VAR_jenkins_api_token   its API token (Manage Jenkins > Users > Security)
"""

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

URL = (os.environ.get("TF_VAR_jenkins_admin_url")
       or (f"https://jenkins.{os.environ['DOMAIN']}" if os.environ.get("DOMAIN") else "")).rstrip("/")
USER = os.environ.get("TF_VAR_jenkins_api_user", "")
TOKEN = os.environ.get("TF_VAR_jenkins_api_token", "")


def die(msg):
    print(f"jenkins_node.py: {msg}", file=sys.stderr)
    sys.exit(1)


def call(method, path, data=None, content_type=None, ok=(200,)):
    """One authenticated request. API-token basic auth is exempt from the
    CSRF crumb, so no crumb dance. Returns (status, body)."""
    if not (URL and USER and TOKEN):
        die("need DOMAIN (or TF_VAR_jenkins_admin_url), TF_VAR_jenkins_api_user and "
            "TF_VAR_jenkins_api_token in the environment (run via make, under `op run`)")
    req = urllib.request.Request(URL + path, data=data, method=method)
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{USER}:{TOKEN}".encode()).decode())
    if content_type:
        req.add_header("Content-Type", content_type)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        if e.code in ok:
            return e.code, e.read().decode()
        die(f"{method} {path} -> HTTP {e.code}: {e.read().decode()[:300]}")
    except urllib.error.URLError as e:
        die(f"{method} {path} -> {e.reason} (is {URL} reachable from here?)")


def exists(name):
    status, _ = call("GET", f"/computer/{urllib.parse.quote(name)}/api/json?tree=displayName", ok=(200, 404))
    return status == 200


def create(name, labels, executors):
    # Same shape as the node the UI creates: permanent agent, inbound launcher,
    # workdir under remoteFS. mode NORMAL so unlabelled jobs may use it too.
    node = {
        "name": name,
        "nodeDescription": "Cloud build agent, managed by infra/ci-agent (OpenTofu)",
        "numExecutors": str(executors),
        "remoteFS": "/home/jenkins/agent",
        "labelString": labels,
        "mode": "NORMAL",
        "launcher": {"stapler-class": "hudson.slaves.JNLPLauncher", "$class": "hudson.slaves.JNLPLauncher"},
        "retentionStrategy": {"stapler-class": "hudson.slaves.RetentionStrategy$Always",
                              "$class": "hudson.slaves.RetentionStrategy$Always"},
        "nodeProperties": {"stapler-class-bag": "true"},
    }
    form = urllib.parse.urlencode({"name": name, "type": "hudson.slaves.DumbSlave", "json": json.dumps(node)})
    call("POST", "/computer/doCreateItem", form.encode(), "application/x-www-form-urlencoded", ok=(200, 302))


def update(name, labels, executors):
    """Edit labels/executors in place through config.xml, leaving everything
    else (and the secret) untouched."""
    _, xml = call("GET", f"/computer/{urllib.parse.quote(name)}/config.xml")
    xml = re.sub(r"<label>.*?</label>", f"<label>{labels}</label>", xml, flags=re.S)
    xml = re.sub(r"<numExecutors>.*?</numExecutors>", f"<numExecutors>{executors}</numExecutors>", xml)
    call("POST", f"/computer/{urllib.parse.quote(name)}/config.xml", xml.encode(), "application/xml")


def secret(name):
    """The JNLP secret is the first <argument> of the node's launch file."""
    _, jnlp = call("GET", f"/computer/{urllib.parse.quote(name)}/jenkins-agent.jnlp")
    m = re.search(r"<argument>([^<]+)</argument>", jnlp)
    if not m:
        die(f"no secret in jenkins-agent.jnlp for {name}")
    return m.group(1)


def delete(name):
    if exists(name):
        call("POST", f"/computer/{urllib.parse.quote(name)}/doDelete", b"", ok=(200, 302))


def list_nodes(label=None):
    _, body = call("GET", "/computer/api/json?tree=computer[displayName,offline,idle,assignedLabels[name]]")
    rows = []
    for c in json.loads(body)["computer"]:
        labels = [l["name"] for l in c.get("assignedLabels", [])]
        if label and label not in labels:
            continue
        rows.append((c["displayName"], "offline" if c["offline"] else "online",
                     "idle" if c["idle"] else "busy", " ".join(l for l in labels if l != c["displayName"])))
    return rows


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "ensure" and len(argv) == 5:
        name, labels, executors = argv[2], argv[3], argv[4]
        (update if exists(name) else create)(name, labels, executors)
        print(f"node {name}: labels='{labels}' executors={executors}")
    elif cmd == "secret":
        # tofu external protocol: JSON object in on stdin, JSON object out.
        query = json.load(sys.stdin)
        print(json.dumps({"secret": secret(query["name"])}))
    elif cmd == "delete" and len(argv) == 3:
        delete(argv[2])
        print(f"node {argv[2]}: deleted")
    elif cmd == "list":
        for row in list_nodes(argv[2] if len(argv) > 2 else None):
            print("%-24s %-8s %-5s %s" % row)
    else:
        die(__doc__)


if __name__ == "__main__":
    main(sys.argv)
