output "wildcard_record" {
  description = "Wildcard DNS record"
  value       = "${digitalocean_record.wildcard.name}.${var.domain} -> ${digitalocean_record.wildcard.value}"
}

output "root_record" {
  description = "Root domain DNS record"
  value       = "${var.domain} -> ${digitalocean_record.root.value}"
}
