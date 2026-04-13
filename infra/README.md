# infra

Infrastructure-as-code managed with [OpenTofu](https://opentofu.org/) / Terraform.

## dns

Manages DNS records on DigitalOcean for the homelab domain.

Creates:
- Wildcard A record (`*.<domain>`) pointing to the homelab machine
- Root A record (`<domain>`) pointing to the homelab machine

### Usage

```bash
cd infra/dns
tofu init
tofu apply
```

### Variables

| Variable | Description |
|---|---|
| `do_token` | DigitalOcean API token |
| `local_ip` | IP address of the homelab machine |
| `domain` | Root domain (default: `dyerwolf.xyz`) |
