provider "digitalocean" {
  token = var.do_token
}

# Import the existing domain (must already exist in DigitalOcean)
data "digitalocean_domain" "main" {
  name = var.domain
}

# Wildcard A record — all subdomains resolve to the homelab machine
resource "digitalocean_record" "wildcard" {
  domain = data.digitalocean_domain.main.id
  type   = "A"
  name   = "*"
  value  = var.local_ip
  ttl    = 300
}

# Bare domain A record
resource "digitalocean_record" "root" {
  domain = data.digitalocean_domain.main.id
  type   = "A"
  name   = "@"
  value  = var.local_ip
  ttl    = 300
}
