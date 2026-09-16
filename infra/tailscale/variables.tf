variable "tailscale_oauth_client_id" {
  description = <<-DESC
    OAuth client ID (tskey-client-...) for the HOMELAB tailnet. Long-lived:
    OAuth clients do not expire.

    One client is shared by this module, ../ci-agent and ../../tailscale. The
    provider narrows it at token-exchange time -- `scopes` in main.tf requests
    policy_file only -- so a token minted here cannot create keys or delete
    devices even though the client is allowed to.

    The client needs tag-scoped scopes for the other two consumers, and a tag
    cannot be selected until it exists in tagOwners, which is written by this
    module. Break that loop by pasting a tagOwners stub into the console once
    before creating the client; `overwrite_existing_content` then lets the first
    apply take the policy over. See ../README.md.
  DESC
  type        = string
  sensitive   = true
}

variable "tailscale_oauth_client_secret" {
  description = "OAuth client secret paired with tailscale_oauth_client_id."
  type        = string
  sensitive   = true
}

variable "jenkins_net_prefixes" {
  description = <<-DESC
    NET_PREFIX of every stack whose Jenkins the agents may reach — the first two
    octets of each stack's traefik-public network, as set in that host's
    homelab.env.

    A LIST, not this host's single NET_PREFIX, because the policy is
    tailnet-wide: one document covers every stack on the tailnet, not just the
    machine tofu happens to run on. common-tofu.mk exports TF_VAR_net_prefix for
    the local host, which is the right input for infra/ci-agent but wrong here.

    Listing a prefix whose stack does not exist yet is harmless — the rule
    simply matches nothing — so the second stack can be here before it is built.
  DESC
  type        = list(string)
  default     = ["172.23", "172.24"]
}

variable "jenkins_host_suffix" {
  description = <<-DESC
    Host part of each controller's address, i.e. JENKINS_HOST_SUFFIX in
    homelab.env; the full address is <prefix>.<suffix>. Exported as
    TF_VAR_jenkins_host_suffix by common-tofu.mk.

    The same pair is interpolated by jenkins/docker-compose.yml (the static
    ipv4_address), tailscale/docker-compose.yml (the advertised /32) and
    infra/ci-agent (jenkins_url), so the route, the ACL and the agent's target
    are all derived from one place and cannot drift.
  DESC
  type        = string
  default     = "255.10"
}

variable "jenkins_ports" {
  description = "Ports on each controller the agents may reach. 8080 = web/API (discovery), 50000 = JNLP callback. An inbound agent needs both."
  type        = string
  default     = "8080,50000"
}

variable "route_supernet" {
  description = <<-DESC
    Route range auto-approved for tag:homelab. An autoApprover covers every
    subset of its range, so the /12 approves both the /32 host routes the subnet
    routers advertise today and any NET_PREFIX chosen later, without a policy
    edit. Narrowing this to a single prefix is how you get a router that
    advertises a route and waits forever for a manual approval.
  DESC
  type        = string
  default     = "172.16.0.0/12"
}

variable "reset_acl_on_destroy" {
  description = <<-DESC
    Whether `tofu destroy` resets the tailnet policy to Tailscale's default.

    FALSE on purpose. The default policy is allow-all with no tagOwners, so a
    reset would strip tag:ci-agent and tag:homelab from a live tailnet: tagged
    nodes lose their identity, advertised routes lose their auto-approval, and
    infra/ci-agent can no longer mint keys. Destroying this module should forget
    the policy, not rewrite the tailnet.
  DESC
  type        = bool
  default     = false
}
