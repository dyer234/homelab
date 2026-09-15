variable "do_token" {
  description = "DigitalOcean API token"
  type        = string
  sensitive   = true
}

variable "tailscale_auth_key" {
  description = <<-DESC
    Pre-minted, TAGGED tailnet auth key (tskey-auth-...) the droplet registers with.

    Generate under Settings > Keys with tag:ci-agent selected:
      Reusable:   YES  - a single-use key is spent by the first registration, so
                         a rebuilt droplet fails with "invalid key ... not valid"
      Ephemeral:  no   - this is a persistent agent; the node must survive a
                         disconnect. Phase 2 (per-build droplets) flips this.
      Expiry:     the key only bounds REGISTRATION, not the node's lifetime.

    The tag is baked into the key, which is why cloud-init passes no
    --advertise-tags. If you ever add that flag it MUST match the key's tags
    exactly or registration is rejected outright.
  DESC
  type        = string
  sensitive   = true
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
  description = "Jenkins node name and tailnet hostname prefix; the agent number is appended."
  type        = string
  default     = "cloud-agent-amd64"
}

# Jenkins nodes are created and deleted by scripts/jenkins_node.py, which reads
# TF_VAR_jenkins_admin_url, TF_VAR_jenkins_api_user and TF_VAR_jenkins_api_token
# straight from the environment (see 1pass.env). They are not declared as
# variables on purpose: values a data source is given are written to
# terraform.tfstate, and an admin API token should not be.

variable "jenkins_url" {
  description = <<-DESC
    Controller URL as reachable FROM the tailnet.

    This is Jenkins' address on the Docker network, reached through the subnet
    router in the homelab's tailscale stack — NOT the host's tailnet IP and not
    the Traefik hostname. Going via the container network is what makes this
    survive the move back to the Linux host unchanged, and what keeps it working
    when the host's own Tailscale is not running.

    Must match the static ipv4_address in jenkins/docker-compose.yml, i.e.
    <NET_PREFIX>.255.10 with NET_PREFIX from the SERVER's homelab.env. Tofu does
    not read those env files; a different prefix means passing this explicitly.
  DESC
  type        = string
  default     = "http://172.23.255.10:8080"
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
