# infra

Infrastructure-as-code managed with [OpenTofu](https://opentofu.org/) / Terraform.

## Secrets

Secret inputs come from a single 1Password item at run time; they are never
written to `terraform.tfvars`. Each module has a `1pass.env` holding `op://`
**references** — no secret values — so those files are committed.

```bash
cd infra/ci-agent
make apply
```

OpenTofu maps `TF_VAR_<name>` onto `variable "<name>"`, so no `.tf` file changes.

Every module has a `Makefile` (one line: `include ../../common-tofu.mk`). Run `make` with
no arguments for the target list. Targets that need variables run under `op run`;
`make fmt`, `make validate` and `make init` call tofu directly, so they never
prompt for credentials they do not read.

Non-secret inputs (`agent_count`, `agent_labels`, `ssh_key_names`, ...) sit in
the same `1pass.env` under `# --- non-secrets ---`, so one file describes a
module; `terraform.tfvars` (gitignored) still works for anything host-specific.

### Creating the item

One Secure Note groups every secret across both modules and the compose apps
that use the same pattern (`../tailscale`, `../homepage`):

```bash
op item create --category "Secure Note" --vault projects --title homelab \
  "do_token[password]=dop_v1_..." \
  "tailscale_client_id[password]=tskey-client-..." \
  "tailscale_client_secret[password]=tskey-client-secret-..." \
  "jenkins_api_token[password]=..."
```

Fields created this way sit at the item's top level, which is what makes the
reference `op://projects/homelab/do_token` resolve. Fields added inside a
**section** need the section in the path (`op://vault/item/section/field`) — if a
reference fails, `op item get homelab --format json` shows the real paths.

Verify one before relying on it:

```bash
op read "op://projects/homelab/do_token"
```

### What this does and does not protect

- Secrets no longer sit in `terraform.tfvars` on disk.
- They do **not** reach `terraform.tfstate` either: the DigitalOcean provider
  stores `user_data` as a SHA1 hash, not plaintext.
- **One exception**: `tailscale_tailnet_key.agent` stores the auth key it mints
  in state in plaintext, the way `terraform_data.jenkins_node`'s JNLP secret
  does. Both are derived, scoped and expiring — the key registers nodes as
  `tag:ci-agent` and dies within 90 days — whereas the OAuth client that mints
  it never touches state. `terraform.tfstate` is gitignored; treat it as a
  secret file regardless.
- They **do** still reach the droplet's `user_data` on DigitalOcean's side, which
  is readable through the DO API for the life of the droplet.
- `tofu plan -out=<file>` writes a plan file containing resolved variable values.
  Don't keep those around.

## dns

Manages DNS records on DigitalOcean for the homelab domain.

Creates:
- Wildcard A record (`*.<domain>`) pointing to the homelab machine
- Root A record (`<domain>`) pointing to the homelab machine

### Usage

```bash
cd infra/dns
make init     # download providers
make apply    # secrets injected from 1Password
```

### Variables

| Variable | Description |
|---|---|
| `do_token` | DigitalOcean API token |
| `local_ip` | IP address of the homelab machine |
| `domain` | Root domain (default: `dyerwolf.xyz`) |

## Two tailnets

**Work tailnet** — `slate-7-ohio` (exit node), `slate-7-ohio-client`, laptops.
Under the original Tailscale account. **Nothing in this repo touches it.** No
policy, no tags, no automation. That separation is the point: an ACL mistake
here cannot strand the work exit node from off-site.

**Homelab tailnet** — a second Tailscale account holding only the subnet router
in `../tailscale` and the build agents from `ci-agent`. Its policy IS automated,
in `infra/tailscale`, because the blast radius is now the homelab.

A device belongs to exactly one tailnet and a client joins one at a time, so:

- Reach homelab services over Traefik (`https://<service>.${DOMAIN}`), not the
  tailnet, while your laptop is on the work tailnet.
- Tailscale SSH into an agent requires being on the homelab tailnet. The
  fallback is the droplet's public IP with the key in `ssh_key_names`.

## tailscale

The homelab tailnet's policy file, as code.

`tailscale_acl` PUTs the **entire** policy — there is no partial update, so a
change made in the console to get something working is silently reverted by the
next `make apply`. Put it in `policy.hujson.tftpl`.

What it provisions:

| Piece | Value |
|---|---|
| `tagOwners` | `tag:homelab`, `tag:ci-agent` (owning **itself** — see below) |
| `autoApprovers.routes` | `172.16.0.0/12` for `tag:homelab` |
| `acls` | members everywhere + `autogroup:internet`; `tag:homelab` everywhere; `tag:ci-agent` to Jenkins only |
| `ssh` | members into `tag:ci-agent` as root/nonroot |

```bash
cd infra/tailscale
make policy   # render without applying
make apply
```

### Variables

| Variable | Description |
|---|---|
| `tailscale_oauth_client_id` / `_secret` | Policy client, `policy_file` scope only |
| `jenkins_net_prefixes` | NET_PREFIX per stack; addresses are derived, tailnet-wide so it is a list |
| `jenkins_host_suffix` | Host part of each controller address (from `JENKINS_HOST_SUFFIX`) |
| `jenkins_ports` | Default `8080,50000` — web/API and JNLP, both required |
| `route_supernet` | Auto-approved range, default `172.16.0.0/12` |
| `reset_acl_on_destroy` | Default `false`; see the variable for why |

### The OAuth client

**One client, shared by all three consumers.** It does not expire, so nothing in
this tree is on a rotation clock.

Admin console → **Settings → OAuth clients** → Generate. (Not Settings → Keys —
that page makes `tskey-auth-` device keys.)

| Scope | Access | Tags | Needed by |
|---|---|---|---|
| **Policy File** | Write | none — not tag-scoped | `infra/tailscale` |
| **Keys → Auth Keys** | Write | `tag:homelab`, `tag:ci-agent` | `tailscale/`, `infra/ci-agent` |
| **Devices → Core** | Write | `tag:ci-agent` | `infra/ci-agent` |

Store as `tailscale_client_id` and `tailscale_client_secret`.

Sharing one client does not mean every module runs with every capability. Both
tofu providers set `scopes`, which narrows the token at exchange time:
`infra/tailscale` requests `policy_file` only, `infra/ci-agent` requests
`auth_keys` + `devices:core`. A token minted by one cannot do the other's job.

`containerboot` is the exception — it presents the secret with no scope
narrowing, and the value sits in the container environment for as long as the
container runs, readable by anything with the host Docker socket
(`docker inspect tailscale`). If that becomes a concern, give `tailscale/` its
own client scoped to `auth_keys` + `tag:homelab` and change one line in its
`1pass.env`; nothing else moves.

Two things that catch people:

- `Devices → Core` must be **Write**. Read passes every check you would run and
  then 403s on the device delete, which only executes at `tofu destroy`.
- The **secret is shown once**; the ID stays visible in the list. The compose
  stack needs the secret alone (it embeds its own client ID); the tofu modules
  need both.

### The bootstrap order, and why it is this way

A tag cannot be selected on an OAuth client until it exists in `tagOwners` — and
`tagOwners` is written by `infra/tailscale`, which needs the client. Break the
loop by seeding the tags by hand, once:

1. **Console → Access Controls**, paste the `tagOwners` block on its own:

   ```jsonc
   "tagOwners": {
     "tag:homelab":  ["autogroup:admin", "tag:homelab"],
     "tag:ci-agent": ["autogroup:admin", "tag:ci-agent"],
   },
   ```

   This is the only hand edit in the whole setup. `infra/tailscale` sets
   `overwrite_existing_content`, so its first apply takes the policy over and
   this stub stops mattering.
2. Create the OAuth client with all three scopes above; store both values.
3. `cd infra/tailscale && make apply`.
4. `cd tailscale && make up && make routes`. The `/32` must show approved.
5. `cd infra/ci-agent && make apply`.

**Every tag owns itself** in `tagOwners`, and that is load-bearing for both of
them. An OAuth client is its own identity, not a user, so `["autogroup:admin"]`
alone does not make the client an owner and every mint fails with
`400 "requested tags [tag:...] are invalid or not permitted"` — which reads like
the tag is missing when it is present but owned by somebody else.

### Routing is the real control

The subnet router advertises `${NET_PREFIX}.${JENKINS_HOST_SUFFIX}/32` — the
Jenkins controller alone, not the `/16`. A compromised build has no **route** to
Sonarr, Navidrome, Redis, n8n or the NAS, not merely no permission. The
`tag:ci-agent` ACL is then defence in depth: both layers must be wrong before a
build reaches anything else.

**One source of truth for that address.** `NET_PREFIX` and `JENKINS_HOST_SUFFIX`
live in `homelab.env`; `common-tofu.mk` exports them as `TF_VAR_net_prefix` and
`TF_VAR_jenkins_host_suffix`, and `common-docker.mk` hands them to compose. Four
things derive from the pair rather than repeating it:

| Consumer | Derives |
|---|---|
| `jenkins/docker-compose.yml` | the controller's static `ipv4_address` |
| `tailscale/docker-compose.yml` | the advertised `/32` route |
| `infra/ci-agent` | `jenkins_url` (empty means derive; set it only to override) |
| `infra/tailscale` | the `tag:ci-agent` ACL destination |

A host that picks a different `/16` gets a consistent route, ACL and agent
target with no edits. `infra/tailscale` takes a **list** of prefixes rather than
the local one, because the policy is tailnet-wide.

Widen `TS_ROUTES` in `../tailscale/docker-compose.yml` to `${NET_PREFIX}.0.0/16`
if you want the whole Docker network on the tailnet again. The autoApprover is
the `/12` supernet, so either qualifies without a policy edit.

Two policy facts worth keeping:

- The subnet router passes an OAuth client secret as `TS_AUTHKEY` with
  `?preauthorized=true&ephemeral=false` appended. Those query parameters are
  valid **only** on an OAuth secret — pasted onto a `tskey-auth-` they become
  part of the key string and invalidate it.
- `--advertise-tags=tag:homelab` on the subnet router is **mandatory**. An OAuth
  client cannot mint an untagged key at all, so without the flag registration
  fails outright instead of producing a user-owned node.
- `preauthorized=true` is not optional either: OAuth-minted keys default it to
  **false**, which leaves the node unapproved and its route unadvertised, with
  nothing saying why.
- Editing `autoApprovers` after a route is already advertised does not
  retroactively approve it — re-advertise (recreate the container) or approve it
  once by hand.

## ci-agent

Provisions a DigitalOcean droplet that joins the tailnet and registers itself as
a Jenkins build agent, with Docker, so the homelab can build **linux/amd64**
images — the host is arm64 and cannot do that natively.

Persistent agents: `TF_VAR_agent_count` long-lived droplets named
`cloud-agent-amd64-1 .. -N`, each with a matching Jenkins node that tofu creates
(and deletes) through the Jenkins API via `scripts/jenkins_node.py`. The node's
JNLP secret is read back from Jenkins into the droplet's cloud-init; nothing is
copied by hand. **Count and labels are edited in `1pass.env`**, then `make apply`:
growing adds droplet+node pairs, shrinking removes the highest-numbered ones,
and a label change is pushed to the existing nodes without touching droplets.
`make nodes` shows Jenkins' view (online/idle/labels) of the fleet and
`make devices` the tailnet's view (device records and last-seen).

Destroying an agent removes all three things it owns: the droplet, the
Jenkins node, and the tailnet device record (`scripts/tailscale_device.py`).
Nothing is left behind to clean up by hand.

### Order of operations

See **The bootstrap order** under `tailscale` above — the two modules share one
sequence, and doing `ci-agent` before `tailscale` fails at the key mint.

Then, per stack: a Jenkins API token for the `admin` user (User → Security → API
Token) stored as `jenkins_api_token`, and `TF_VAR_agent_count` set in `1pass.env`.

### Variables

| Variable | Description |
|---|---|
| `do_token` | DigitalOcean API token |
| `tailscale_oauth_client_id` / `_secret` | ci-agent OAuth client; mints one single-use key per agent and deletes device records |
| `tailscale_key_expiry` | Registration window for each minted key, seconds (default 7776000 = 90 days, the cap) |
| `jenkins_url` | Jenkins as the *agents* reach it, over the tailnet (default `http://172.23.255.10:8080`) |
| `agent_count` / `agent_labels` / `agent_executors` | The fleet; set in `1pass.env` |
| `agent_name_prefix` | Node and hostname prefix (default `cloud-agent-amd64`) |
| `TF_VAR_jenkins_admin_url` / `_api_user` / `_api_token` | Jenkins as *tofu* reaches it plus the admin token; env-only, read by `scripts/jenkins_node.py`, never in state |
| `region` / `size` / `image` | Droplet shape (defaults `nyc3` / `s-2vcpu-4gb` / `ubuntu-24-04-x64`) |
| `ssh_key_names` | Optional DO SSH keys; Tailscale SSH is the primary path |

### A second stack

Another homelab on its own machine, its own `NET_PREFIX` and its own Jenkins,
with agents managed by a separate copy of this module. Most of it already works:
`autoApprovers` covers `172.16.0.0/12`, so the new router's route auto-approves,
and `NET_PREFIX` / `TS_HOSTNAME` are per-host variables already.

What has to be done per stack:

| Setting | Where | Why |
|---|---|---|
| `TF_VAR_agent_name_prefix` | `1pass.env` | **Required, not cosmetic** — see below |
| `TF_VAR_jenkins_url` | `1pass.env` | `<NET_PREFIX>.255.10:8080` for *that* stack |
| `NET_PREFIX`, `TS_HOSTNAME` | `homelab.env` / `homelab.local.env` | distinct subnet and router node |
| The controller's address | tailnet policy `acls` | add to the `tag:ci-agent` `dst` list |
| 1Password fields | the `homelab` item | a Jenkins token per controller |

**`agent_name_prefix` is the one that bites.** Every fleet carries `tag:ci-agent`,
so the tailnet hostname is the *only* thing separating one stack's agents from
another's. Two stacks at the shared default means `tofu destroy` in one deletes
the other's **live** device record — `scripts/tailscale_device.py` matches on
hostname and removes every match. The losing agent drops off the tailnet with no
error of its own; the only clue is a warning in the destroy output of the stack
that did it.

**On reachability.** One tag means any agent can open a connection to any
controller in the `dst` list. That is a deliberate trade: an agent cannot
*register* with the wrong controller, because Jenkins derives the JNLP secret by
HMAC over the node name using the controller's own instance key, so the same
node name yields a different secret on each controller and the handshake fails.
If you later want the network to enforce the boundary as well, give each stack
its own tag (`tag:ci-agent`, `tag:ci-agent-2`), add a `tagOwners` entry that owns
itself, and split the rule — the module reads the tag from
`tailscale_tailnet_key.agent` in `main.tf`, which is the only place it appears.

Running two stacks on the **same machine** is a different and larger problem —
`traefik-public` is a hardcoded network name declared `external: true` by every
other stack, so the second one silently joins the first one's subnet instead of
getting its own. Container names and published ports collide too. Not supported.

### Gotchas

- **`--accept-routes` on the agent is load-bearing.** The controller is at a
  Docker network address behind a subnet router, and a node ignores advertised
  routes unless it opts in. Without the flag the agent joins the tailnet fine and
  then cannot reach Jenkins, with nothing in the logs pointing at the cause.
- Two addresses must agree: `ipv4_address` in `jenkins/docker-compose.yml` and
  `jenkins_url` here. Changing one means changing both.
- `tofu apply` returns when the droplet is **created**, not when the agent
  **connects**. Cloud-init still has to install Tailscale and Docker.
  `tofu output verify` prints the commands to check.
- The JNLP secret sits in the droplet's `user_data`, readable through the DO API,
  and stays valid as long as the Jenkins node object exists. Deleting the node in
  Jenkins is what revokes it — not destroying the droplet.
- **Keys are single-use and per-agent**, so a key is spent the moment its
  droplet registers and every plan wants to remint it
  (`recreate_if_invalid = "always"`). `ignore_changes = [user_data]` on the
  droplet is the counterpart — without it, each apply would replace the whole
  fleet.
- **The cost of that `ignore_changes`**: edits to `cloud-init.yaml.tftpl`,
  `agent_base_image` or `jenkins_url` **do not reach existing droplets**. They
  apply to agents created afterwards. Roll a change with
  `tofu apply -replace='digitalocean_droplet.agent["cloud-agent-amd64-1"]'`,
  one agent at a time, which drains rather than taking the fleet out at once.
- Do **not** set `recreate_if_invalid = "never"` on these keys. It is correct
  for one shared reusable key and wrong here: the spent key stays in state and
  the next rebuild fails with `invalid key: API key ... not valid`, which reads
  like a credential problem rather than a consumed one.
- **Tailnet device cleanup runs after the droplet is destroyed**, enforced by
  `depends_on = [terraform_data.tailnet_device]` on the droplet (tofu tears down
  in reverse dependency order). The other order would kick a still-running
  droplet off the tailnet, and if its destroy then failed you would have a live
  box with no Tailscale SSH — on exactly the machine you need to get into.
- Device deletion matches on the tailnet **hostname**, not the MagicDNS name.
  The coordination server deduplicates names, so an agent rebuilt while a stale
  record exists comes back as `cloud-agent-amd64-1-1`; matching on the name
  would skip precisely the records worth removing.
- Jenkins node objects live in `jenkins/data/nodes/`, which is gitignored. Node
  registration is not reproducible from this repo — script it with
  `jenkins-cli create-node` or adopt JCasC if that starts to hurt.
