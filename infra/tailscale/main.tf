provider "tailscale" {
  oauth_client_id     = var.tailscale_oauth_client_id
  oauth_client_secret = var.tailscale_oauth_client_secret
  scopes              = ["policy_file"]
}

locals {
  # One controller per stack, assembled from the same prefix/suffix pair the
  # compose files and infra/ci-agent use.
  jenkins_controllers = [for p in var.jenkins_net_prefixes : "${p}.${var.jenkins_host_suffix}"]

  policy = templatefile("${path.module}/policy.hujson.tftpl", {
    jenkins_controllers = local.jenkins_controllers
    jenkins_ports       = var.jenkins_ports
    route_supernet      = var.route_supernet
  })
}

# The whole tailnet policy, as one document.
#
# There is no partial update: tailscale_acl PUTs the entire policy file, so
# anything not in policy.hujson.tftpl is gone after an apply. That is the point
# -- the file in this repo is the source of truth -- but it means a change made
# in the admin console to get something working is silently reverted by the next
# apply. Put it in the template.
#
# This was hand-maintained before, and was moved here only once the homelab got
# its own tailnet. On the shared tailnet a bad policy could strand the work exit
# node from off-site; here the blast radius is the homelab.
resource "tailscale_acl" "homelab" {
  acl = local.policy

  # Required for the FIRST apply, which takes over a policy this module did not
  # write. Without it the provider refuses to clobber existing content.
  overwrite_existing_content = true

  # See the variable: resetting on destroy would strip the tags off a live
  # tailnet rather than simply forgetting the policy.
  reset_acl_on_destroy = var.reset_acl_on_destroy

  lifecycle {
    # HuJSON tolerates a trailing comma, but an EMPTY dst list is not a policy
    # Tailscale will accept, and the failure arrives as a generic 400 from the
    # API rather than anything pointing at this variable.
    precondition {
      condition     = length(var.jenkins_net_prefixes) > 0
      error_message = "jenkins_net_prefixes is empty: the tag:ci-agent rule would have no destination and the policy would be rejected."
    }
  }
}
