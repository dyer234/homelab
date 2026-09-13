output "droplet_ip" {
  description = "Public IPv4. Useful for the DO console only — the agent talks to Jenkins over the tailnet, not this address."
  value       = digitalocean_droplet.agent.ipv4_address
}

output "agent_name" {
  description = "Jenkins node name / tailnet hostname"
  value       = var.agent_name
}

output "verify" {
  description = "How to check the agent actually came up"
  value       = <<-EOT
    tofu apply returns once the droplet is CREATED, not once the agent CONNECTS.
    Cloud-init still has to install Tailscale, Docker and start the agent.

      tailscale status | grep ${var.agent_name}      # node joined the tailnet
      ssh root@${var.agent_name}                     # via Tailscale SSH
      ssh root@${var.agent_name} cloud-init status --wait
      ssh root@${var.agent_name} docker images ci-agent   # agent image built
      ssh root@${var.agent_name} docker logs jenkins-agent

    Docker access from inside the agent is the thing most likely to be broken,
    and it fails at build time rather than at boot. Check it directly:

      ssh root@${var.agent_name} docker exec jenkins-agent docker version

    Then Manage Jenkins > Nodes — the node should flip to online.
  EOT
}
