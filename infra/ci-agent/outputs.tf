output "agents" {
  description = "Agent name -> public IPv4. The IP is for the DO console only; agents talk to Jenkins over the tailnet."
  value       = { for name, d in digitalocean_droplet.agent : name => d.ipv4_address }
}

output "verify" {
  description = "How to check an agent actually came up"
  value       = <<-EOT
    tofu apply returns once the droplets are CREATED, not once the agents CONNECT.
    Cloud-init still has to install Tailscale, Docker and start the agent.

      make nodes                                     # Jenkins' view: online/idle per agent
      tailscale status | grep ${var.agent_name_prefix}   # nodes joined the tailnet
      ssh root@<agent>                               # via Tailscale SSH
      ssh root@<agent> cloud-init status --wait
      ssh root@<agent> docker logs jenkins-agent

    Docker access from inside the agent is the thing most likely to be broken,
    and it fails at build time rather than at boot. Check it directly:

      ssh root@<agent> docker exec jenkins-agent docker version
  EOT
}
