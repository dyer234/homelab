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

variable "agent_name" {
  description = "Jenkins node name. Must match the node created in Jenkins exactly — the JNLP handshake is rejected otherwise."
  type        = string
  default     = "cloud-amd64"
}

variable "jenkins_agent_secret" {
  description = <<-DESC
    JNLP secret for the Jenkins node named var.agent_name. Jenkins mints this when
    the node is created (Manage Jenkins > Nodes > the node > it is shown in the
    connection command).

    This lands in the droplet's user_data, which is readable through the DO API
    for the life of the droplet, and unlike the tailnet key it stays valid as
    long as the Jenkins node object exists. Deleting the node in Jenkins is what
    actually revokes it.
  DESC
  type        = string
  sensitive   = true
}

variable "jenkins_url" {
  description = <<-DESC
    Controller URL as reachable FROM the tailnet.

    This is Jenkins' address on the Docker network, reached through the subnet
    router in the homelab's tailscale stack — NOT the host's tailnet IP and not
    the Traefik hostname. Going via the container network is what makes this
    survive the move back to the Linux host unchanged, and what keeps it working
    when the host's own Tailscale is not running.

    Must match the static ipv4_address in jenkins/docker-compose.yml.
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
