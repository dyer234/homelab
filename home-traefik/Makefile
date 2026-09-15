include ../common-docker.mk

.PHONY: network certs routers

# DOMAIN as the launchers resolve it: homelab.local.env wins over homelab.env.
DOMAIN := $(shell sed -n 's/^DOMAIN=//p' ../homelab.local.env ../homelab.env 2>/dev/null | head -1)

network: ## Show the traefik-public subnet and every container on it
	@docker network inspect traefik-public --format \
	  '{{(index .IPAM.Config 0).Subnet}}{{"\n"}}{{range .Containers}}{{printf "%-20s %s\n" .Name .IPv4Address}}{{end}}' \
	  | sort -t. -k4,4n

certs: ## List certificates Let's Encrypt has issued (from letsencrypt/acme.json)
	@python3 -c 'import json; \
	  d=json.load(open("letsencrypt/acme.json")); \
	  certs=[c["domain"] for r in d.values() for c in (r.get("Certificates") or [])]; \
	  print("no certificates issued") if not certs else \
	  [print(c["main"], *c.get("sans", [])) for c in certs]'

routers: ## List HTTP routers and their rules, from the dashboard API
	@curl -sk --resolve '$(DOMAIN):443:127.0.0.1' 'https://$(DOMAIN)/traefik/api/http/routers' | \
	  python3 -c 'import json,sys; \
	    [print("%-8s %-34s %s" % (r["status"], r["name"], r["rule"])) \
	     for r in sorted(json.load(sys.stdin), key=lambda r: r["name"])]'
