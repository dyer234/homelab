variable "do_token" {
  description = "DigitalOcean API token"
  type        = string
  sensitive   = true
}

variable "tailscale_oauth_client_id" {
  description = <<-DESC
    OAuth client ID (tskey-client-...) for the HOMELAB tailnet. Long-lived:
    OAuth clients do not expire.

    The same client ../tailscale and ../../tailscale use. `scopes` in main.tf
    requests auth_keys and devices:core only, so a token minted by this module
    cannot rewrite the tailnet policy.

    Scopes the client must carry for this module:
      auth_keys      write   mints one single-use key per agent
      devices:core   write   deletes the device record on destroy
                             (read alone returns 403 on DELETE /device/<id>,
                             and that only runs at destroy)

    THE TAG MUST OWN ITSELF. An OAuth client is its own identity, not a user, so
    `"tag:ci-agent": ["autogroup:admin"]` in tagOwners does not make the client
    an owner and every key request is rejected with
      400 "requested tags [tag:ci-agent] are invalid or not permitted"
    which reads like the tag is missing when it is present but owned by
    somebody else. See ../tailscale/policy.hujson.tftpl.
  DESC
  type        = string
  sensitive   = true
}

variable "tailscale_oauth_client_secret" {
  description = "OAuth client secret paired with tailscale_oauth_client_id."
  type        = string
  sensitive   = true
}

variable "tailscale_key_expiry" {
  description = <<-DESC
    Lifetime in seconds of the auth key tofu mints, capped by Tailscale at
    7776000 (90 days).

    This bounds REGISTRATION ONLY. An agent that has already joined stays on the
    tailnet indefinitely: the key is tagged, and tagged nodes have key expiry
    disabled. So an expired key breaks `tofu apply` for a NEW or REBUILT droplet
    and does nothing at all to the running fleet.
  DESC
  type        = number
  default     = 7776000
}

# --- the fleet: set these in 1pass.env (TF_VAR_agent_count etc.), not here ---

variable "agent_count" {
  description = "How many agents to run. Names are <agent_name_prefix>-1 .. -N; shrinking removes the highest numbers."
  type        = number
  default     = 1
}

variable "agent_labels" {
  description = "Space-separated Jenkins labels every agent gets. Pipelines select agents with `agent { label '...' }`."
  type        = string
  default     = "linux docker amd64"
}

variable "agent_executors" {
  description = "Concurrent builds per agent."
  type        = number
  default     = 1
}

variable "agent_name_prefix" {
  description = <<-DESC
    Jenkins node name and tailnet hostname prefix; the agent number is appended.
    Changing it REPLACES every agent.

    MUST BE UNIQUE PER STACK. Every fleet shares tag:ci-agent, so the hostname
    is the only thing that distinguishes one stack's agents from another's on
    the tailnet -- there is no second identity to fall back on.

    Two stacks left at this default is a data-loss bug, not a cosmetic clash:
    scripts/tailscale_device.py matches on hostname and deletes EVERY match, so
    `tofu destroy` in one stack removes the other stack's LIVE device record.
    That agent drops off the tailnet mid-build with nothing pointing at the
    cause. MagicDNS also dedupes the name, so the survivor comes back as
    <prefix>-1-1 and stops matching its own cleanup.
  DESC
  type        = string
  default     = "cloud-agent-amd64"
}

# Jenkins nodes are created and deleted by scripts/jenkins_node.py, which reads
# TF_VAR_jenkins_admin_url, TF_VAR_jenkins_api_user and TF_VAR_jenkins_api_token
# straight from the environment (see 1pass.env). They are not declared as
# variables on purpose: values a data source is given are written to
# terraform.tfstate, and an admin API token should not be.

variable "net_prefix" {
  description = <<-DESC
    First two octets of this stack's traefik-public network, i.e. NET_PREFIX
    from homelab.env. Exported as TF_VAR_net_prefix by common-tofu.mk, which
    reads homelab.local.env then homelab.env, so running under `make` picks up
    the same value compose uses. The default is only a fallback for a bare
    `tofu` invocation outside make.
  DESC
  type        = string
  default     = "172.23"
}

variable "jenkins_host_suffix" {
  description = "Host part of the controller's address on that network (JENKINS_HOST_SUFFIX in homelab.env). Also exported by common-tofu.mk."
  type        = string
  default     = "255.10"
}

variable "jenkins_url" {
  description = <<-DESC
    Controller URL as reachable FROM the tailnet. EMPTY MEANS DERIVE IT from
    net_prefix and jenkins_host_suffix, which is what you want; set this only to
    override.

    This is Jenkins' address on the Docker network, reached through the subnet
    router in the homelab's tailscale stack — NOT the host's tailnet IP and not
    the Traefik hostname. Going via the container network is what makes this
    survive the move back to the Linux host unchanged, and what keeps it working
    when the host's own Tailscale is not running.

    The subnet router advertises exactly this address as a /32, and the
    tag:ci-agent rule in infra/tailscale permits exactly this address. All three
    derive from the same two variables so they cannot drift.
  DESC
  type        = string
  default     = ""
}

variable "region" {
  description = "DigitalOcean region"
  type        = string
  default     = "nyc3"
}

variable "size" {
  description = "Droplet size. Docker image builds want headroom; the default is the smallest size that is not painful."
  type        = string
  default     = "s-2vcpu-4gb"
}

variable "image" {
  description = "Droplet image. x64 on purpose — building linux/amd64 natively is the entire point of this agent, since the homelab host is arm64."
  type        = string
  default     = "ubuntu-24-04-x64"
}

variable "ssh_key_names" {
  description = "Names of existing DigitalOcean SSH keys to add to the droplet. Optional — Tailscale SSH is the primary access path (the Tailscale SSH rule granting access into tag:ci-agent is maintained by hand in the admin console ACL)."
  type        = list(string)
  default     = []
}

variable "agent_base_image" {
  description = <<-DESC
    Base image the agent image is built FROM (see cloud-init.yaml.tftpl).

    Kept as a variable because this tag wants pinning and currently is not. This
    repo has already been burned once by a floating tag — see the comment at
    home-traefik/docker-compose.yml, where a CI build shadowed traefik:latest and
    broke routing. Pin to a specific inbound-agent build once one has proven
    itself here; the tags are listed on Docker Hub as e.g.
    jenkins/inbound-agent:3309.v27b_9314fd1a_4-1-jdk21.

    The JDK major version must satisfy the controller's minimum remoting version,
    so do not drop below jdk17.
  DESC
  type        = string
  default     = "jenkins/inbound-agent:latest-jdk21"
}
