provider "digitalocean" {
  token = var.do_token
}

data "digitalocean_ssh_key" "keys" {
  for_each = toset(var.ssh_key_names)
  name     = each.value
}

# NOTE: no tailscale provider here, and no tailscale_tailnet_key resource.
#
# The key is supplied as var.tailscale_auth_key — a PRE-MINTED, TAGGED device
# auth key (tskey-auth-...), generated once in the admin console under
# Settings > Keys with tag:ci-agent selected.
#
# Why not mint it here with an OAuth client, which is the tidier pattern:
# registering with an OAuth client secret was rejected with
#   400 "requested tags [tag:...] are invalid or not permitted"
# against a client that demonstrably carried the tag, with the tag live in
# tagOwners. Unexplained. A pre-minted key is the path that actually works, and
# it removes the OAuth client from this module's critical path entirely.
#
# Generate it REUSABLE. A single-use key is consumed by the first successful
# registration, so any droplet rebuild — or a `tofu destroy`/`apply` cycle —
# fails to register with "invalid key: API key ... not valid", which reads like
# a credential problem rather than a spent one.

locals {
  user_data = templatefile("${path.module}/cloud-init.yaml.tftpl", {
    authkey          = var.tailscale_auth_key
    hostname         = var.agent_name
    jenkins_url      = var.jenkins_url
    agent_name       = var.agent_name
    agent_secret     = var.jenkins_agent_secret
    agent_base_image = var.agent_base_image
  })
}

resource "digitalocean_droplet" "agent" {
  name     = var.agent_name
  image    = var.image
  region   = var.region
  size     = var.size
  ssh_keys = [for k in data.digitalocean_ssh_key.keys : k.id]

  tags = ["ci-agent"]

  user_data = local.user_data

  lifecycle {
    # cloud-init parses user_data strictly and, on a single non-ASCII byte,
    # fails with "unacceptable character #x0080" and DISCARDS THE ENTIRE
    # DOCUMENT. The droplet then boots perfectly with nothing installed, no
    # tailnet, no agent, and no error visible anywhere except
    # /var/log/cloud-init.log on a box you cannot reach because the thing that
    # was meant to give you access was in the document that got discarded.
    #
    # Four em dashes in comments cost three droplets. Fail the plan instead.
    precondition {
      condition     = can(regex("^[[:ascii:]]*$", local.user_data))
      error_message = "cloud-init.yaml.tftpl rendered non-ASCII characters. cloud-init will silently discard the whole document. Find them with: python3 -c \"print([(i,c) for i,c in enumerate(open('cloud-init.yaml.tftpl').read()) if ord(c)>127])\""
    }
  }
}
