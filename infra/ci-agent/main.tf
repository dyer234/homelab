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
  # cloud-agent-amd64-1 .. -N. A map keyed by name so adding or removing an
  # agent touches only that agent's resources.
  agents = { for n in range(1, var.agent_count + 1) : "${var.agent_name_prefix}-${n}" => n }

  user_data = {
    for name, n in local.agents : name => templatefile("${path.module}/cloud-init.yaml.tftpl", {
      authkey          = var.tailscale_auth_key
      hostname         = name
      jenkins_url      = var.jenkins_url
      agent_name       = name
      agent_secret     = data.external.jenkins_secret[name].result.secret
      agent_base_image = var.agent_base_image
    })
  }
}

# The Jenkins side of each agent: a node object, created with the droplet and
# deleted with it. Its lifetime is tracked in state like any resource; the API
# calls live in scripts/jenkins_node.py.
resource "terraform_data" "jenkins_node" {
  for_each = local.agents

  input = each.key

  provisioner "local-exec" {
    command = "python3 '${path.module}/scripts/jenkins_node.py' ensure '${each.key}' '${var.agent_labels}' '${var.agent_executors}'"
  }

  provisioner "local-exec" {
    when    = destroy
    command = "python3 '${path.module}/scripts/jenkins_node.py' delete '${self.output}'"
  }
}

# Labels/executors changes are pushed to the existing node in place (no new
# secret, so the droplet is untouched). Separate from the node resource so a
# label edit does not replace it.
resource "terraform_data" "jenkins_node_config" {
  for_each = local.agents

  triggers_replace = [var.agent_labels, var.agent_executors]

  provisioner "local-exec" {
    command = "python3 '${path.module}/scripts/jenkins_node.py' ensure '${each.key}' '${var.agent_labels}' '${var.agent_executors}'"
  }

  depends_on = [terraform_data.jenkins_node]
}

# The node's JNLP secret, read back from Jenkins. Referencing the node's
# `output` (unknown until it is applied) is what makes tofu wait for the node
# to exist before reading.
data "external" "jenkins_secret" {
  for_each = local.agents

  program = ["python3", "${path.module}/scripts/jenkins_node.py", "secret"]
  query   = { name = terraform_data.jenkins_node[each.key].output }
}

resource "digitalocean_droplet" "agent" {
  for_each = local.agents

  name     = each.key
  image    = var.image
  region   = var.region
  size     = var.size
  ssh_keys = [for k in data.digitalocean_ssh_key.keys : k.id]

  tags = ["ci-agent"]

  user_data = local.user_data[each.key]

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
      condition     = can(regex("^[[:ascii:]]*$", local.user_data[each.key]))
      error_message = "cloud-init.yaml.tftpl rendered non-ASCII characters. cloud-init will silently discard the whole document. Find them with: python3 -c \"print([(i,c) for i,c in enumerate(open('cloud-init.yaml.tftpl').read()) if ord(c)>127])\""
    }
  }
}
