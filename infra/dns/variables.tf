variable "do_token" {
  description = "DigitalOcean API token"
  type        = string
  sensitive   = true
}

variable "local_ip" {
  description = "Local IP address of the homelab machine running traefik"
  type        = string
}

variable "domain" {
  description = "Root domain name"
  type        = string
  default     = "dyerwolf.xyz"
}
