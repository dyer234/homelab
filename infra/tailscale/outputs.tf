output "policy" {
  description = "The rendered policy, as applied. `tofu output -raw policy` to diff against the console."
  value       = local.policy
}

output "jenkins_reachable_by_agents" {
  description = "What tag:ci-agent is permitted to reach, for a quick sanity check against jenkins_url in each stack's infra/ci-agent."
  value       = [for ip in local.jenkins_controllers : "${ip}:${var.jenkins_ports}"]
}
