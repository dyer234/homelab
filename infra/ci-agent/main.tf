provider "digitalocean" {
  token = var.do_token
}

data "digitalocean_ssh_key" "keys" {
  for_each = toset(var.ssh_key_names)
  name     = each.value
}

provider "tailscale" {
  oauth_client_id     = var.tailscale_oauth_client_id
  oauth_client_secret = var.tailscale_oauth_client_secret
  scopes              = ["auth_keys", "devices:core"]
}

# One registration key PER AGENT, single-use, minted from the OAuth client.
# No key is shared between droplets.
#
# SINGLE-USE (reusable = false): a key is spent by the registration it was
# minted for, so a leaked user_data blob is worth nothing once the droplet has
# booted. A rebuild gets a freshly minted key rather than re-presenting a spent
# one, which is what makes single-use workable here at all.
#
# NOT EPHEMERAL (ephemeral = false): the node must survive a disconnect. An
# ephemeral node is swept by the coordination server minutes after it goes
# offline, so a network blip during a long build would delete the agent out from
# under Jenkins. Device records are removed explicitly instead, on destroy --
# see terraform_data.tailnet_device below.
resource "tailscale_tailnet_key" "agent" {
  for_each = local.agents

  reusable      = false
  ephemeral     = false
  preauthorized = true
  tags          = ["tag:ci-agent"]
  expiry        = var.tailscale_key_expiry
  description   = "ci-agent ${each.key}"

  # A single-use key reports itself invalid the moment its droplet registers, so
  # on the default setting EVERY plan wants to recreate EVERY key. Paired with
  # ignore_changes on the droplet's user_data below, that is exactly what we
  # want: keys are refreshed for free, and a droplet that is actually rebuilt
  # picks up a live key instead of the spent one sitting in state.
  #
  # Do NOT set this to "never" here: the key would stay spent in state, and the
  # next rebuild would fail registration with
  # "invalid key: API key ... not valid" -- which reads like a credential
  # problem rather than a consumed one.
  recreate_if_invalid = "always"
}

locals {
  # Jenkins' address on the Docker network, assembled from the same pair the
  # compose files interpolate, so tofu and compose cannot disagree about it.
  jenkins_url = var.jenkins_url != "" ? var.jenkins_url : "http://${var.net_prefix}.${var.jenkins_host_suffix}:8080"

  # cloud-agent-amd64-1 .. -N. A map keyed by name so adding or removing an
  # agent touches only that agent's resources.
  agents = { for n in range(1, var.agent_count + 1) : "${var.agent_name_prefix}-${n}" => n }

  user_data = {
    for name, n in local.agents : name => templatefile("${path.module}/cloud-init.yaml.tftpl", {
      authkey          = tailscale_tailnet_key.agent[name].key
      hostname         = name
      jenkins_url      = local.jenkins_url
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

# Cleanup of the tailnet device record, which nothing else owns.
#
# The droplet registers ITSELF from cloud-init, so the device is not a resource
# tofu creates and cannot be one it tracks -- there is no create side here, only
# a destroy side. Without it, every destroyed or rebuilt agent leaves an offline
# node behind, and those accumulate against the free plan's device limit.
#
# The obvious alternative is an ephemeral auth key, which makes the coordination
# server sweep the node a few minutes after it disconnects. Rejected on purpose:
# these agents are persistent, and a node that vanishes during a network blip
# takes a running build with it. Explicit deletion costs one API call and has no
# effect on a healthy agent.
#
# `input`/`self.output` rather than each.key because a destroy-time provisioner
# may not reference anything but `self` -- the same trick terraform_data
# .jenkins_node uses above.
resource "terraform_data" "tailnet_device" {
  for_each = local.agents

  input = each.key

  provisioner "local-exec" {
    when    = destroy
    command = "python3 '${path.module}/scripts/tailscale_device.py' delete '${self.output}'"
  }
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

  # Ordering for DESTROY, not create. Tofu tears down in reverse dependency
  # order, so depending on the cleanup resource means the droplet dies first and
  # the device record is removed after. The other order deletes the device out
  # from under a droplet that still exists, and if the droplet destroy then
  # fails you are left with a live box that has just been kicked off the tailnet
  # -- i.e. no Tailscale SSH, on exactly the machine you now need to get into.
  depends_on = [terraform_data.tailnet_device]

  lifecycle {
    # THE COUNTERPART TO recreate_if_invalid = "always". Keys are single-use, so
    # they are reminted on every apply and user_data changes every time. Without
    # this, each apply would replace the entire running fleet.
    #
    # The cost is real and worth knowing: edits to cloud-init.yaml.tftpl,
    # agent_base_image or jenkins_url no longer reach EXISTING droplets. They
    # apply to agents created afterwards. To roll a change across the fleet,
    # replace the droplets deliberately:
    #   tofu apply -replace='digitalocean_droplet.agent["cloud-agent-amd64-1"]'
    # which is the right shape anyway: it drains one agent at a time instead of
    # taking the whole fleet out at once.
    ignore_changes = [user_data]

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
