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

Non-secret inputs (`agent_name`, `ssh_key_names`, `region`, ...) stay in
`terraform.tfvars`, which remains gitignored.

### Creating the item

One Secure Note groups every secret across both modules and the compose apps
that use the same pattern (`../tailscale`, `../homepage`):

```bash
op item create --category "Secure Note" --vault projects --title homelab \
  "do_token[password]=dop_v1_..." \
  "tailscale_auth_key_ci_agent[password]=tskey-auth-..." \
  "tailscale_auth_key_docker_subnet[password]=tskey-auth-..." \
  "jenkins_agent_secret[password]=..." \
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

## Tailnet policy (by hand, in the admin console)

Tags, ACLs, Tailscale SSH rules and route auto-approval are **not** managed from
this repo. They are edited by hand under Access Controls in the admin console.
There used to be an OpenTofu module here for the policy file; it was dropped in
favour of maintaining it manually, so nothing in this tree will overwrite it.

What the console needs to contain for the rest of this tree to work:

| Tag | Used by | Console must grant |
|---|---|---|
| `tag:homelab` | The host and the subnet-router container in `../tailscale` | `tagOwners` entry; `autoApprovers.routes["172.23.0.0/16"]` |
| `tag:ci-agent` | Cloud build agents | `tagOwners` entry; a Tailscale SSH rule into it |

Build agents are pointed at the **container** path only — Jenkins' address on the
Docker network, routed by the `tag:homelab` subnet router. That path behaves
identically on the Mac today and on the Linux host later, and it is up whenever
the homelab is up, regardless of whether the host's own Tailscale is running.

The tags are **not** access control. The tailnet is flat — every device on it is
trusted and the ACL is the default allow-all. Tags exist because `tagOwners` is
what makes them issuable at all, and because `autoApprovers` is keyed to them.

An auth key's tags must match `--advertise-tags` on the node **exactly**, or
registration fails with `requested tags [...] are invalid or not permitted`.
Editing `autoApprovers` after a route is already advertised does not
retroactively approve it — re-advertise (recreate the container) or approve it
once by hand on the machine.

## ci-agent

Provisions a DigitalOcean droplet that joins the tailnet and registers itself as
a Jenkins build agent, with Docker, so the homelab can build **linux/amd64**
images — the host is arm64 and cannot do that natively.

Currently a **persistent** agent: one long-lived droplet. The ephemeral
per-build design (`ephemeral = true` on the tailnet key, droplet created and
destroyed inside the build) is the intended next step; `main.tf` marks the two
places that change.

### Order of operations

There is a genuine chicken-and-egg here — a tag cannot be assigned to anything
until the console policy declares it in `tagOwners`.

1. **Declare the tags in the admin console** (Access Controls): `tagOwners` for
   `tag:homelab` and `tag:ci-agent`, `autoApprovers.routes["172.23.0.0/16"]`
   for `tag:homelab`, and a Tailscale SSH rule into `tag:ci-agent`. Do this
   **first**, so the subnet route is approved the moment the container
   advertises it.
2. **Tag the host**: Machines → the host → Edit tags → `tag:homelab`. Tagging also
   disables key expiry, which is what you want for a machine that would otherwise
   drop off the tailnet every 180 days.
3. **Bring up the subnet router**: generate a reusable, pre-approved auth key
   tagged `tag:homelab`, store it in the 1Password item as
   `tailscale_auth_key_docker_subnet` (referenced from `tailscale/1pass.env`),
   then `cd tailscale && make up && make routes`. The route must show as
   approved.
4. **Rebuild Jenkins** so it has plugins and `tofu`, and picks up its static IP:
   `cd jenkins && docker compose up -d --build`.
5. **Create the Jenkins node**: Manage Jenkins → Nodes → New Node, name it to
   match `var.agent_name`, launch method "Launch agent by connecting it to the
   controller". Copy the secret it shows you.
6. Put that secret in the 1Password item as `jenkins_agent_secret`, generate a
   reusable auth key tagged `tag:ci-agent` as `tailscale_auth_key_ci_agent`,
   then `cd infra/ci-agent && make apply`.

### Variables

| Variable | Description |
|---|---|
| `do_token` | DigitalOcean API token |
| `tailscale_auth_key` | Pre-minted, reusable auth key tagged `tag:ci-agent` |
| `jenkins_url` | Jenkins on the Docker network (default `http://172.23.255.10:8080`) |
| `agent_name` | Jenkins node name; must match exactly (default `cloud-amd64`) |
| `jenkins_agent_secret` | JNLP secret from the Jenkins node |
| `region` / `size` / `image` | Droplet shape (defaults `nyc3` / `s-2vcpu-4gb` / `ubuntu-24-04-x64`) |
| `ssh_key_names` | Optional DO SSH keys; Tailscale SSH is the primary path |

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
- `recreate_if_invalid = "never"` on the tailnet key is load-bearing. The key
  goes invalid 15 minutes after apply; without that setting the next plan wants
  to recreate it, which changes `user_data` and **replaces the running droplet**.
- Jenkins node objects live in `jenkins/data/nodes/`, which is gitignored. Node
  registration is not reproducible from this repo — script it with
  `jenkins-cli create-node` or adopt JCasC if that starts to hurt.
