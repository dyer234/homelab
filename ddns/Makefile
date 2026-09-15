include ../common-docker.mk

.PHONY: status ip records

status: ## Last cycle's result as the Homepage card sees it
	@$(COMPOSE) exec ddns wget -qO- http://127.0.0.1:8080/status.json

ip: ## This host's public IP vs what DNS answers for each managed record
	@ip=$$(curl -fsS --max-time 10 https://api.ipify.org); echo "public IP: $$ip"; \
	  domain=$$(sed -n 's/^DOMAIN=//p' ../homelab.local.env ../homelab.env | head -1); \
	  names=$$(sed -n 's/^RECORD_NAMES=//p' 1pass.env); \
	  for n in $$(echo "$${names:-@,*}" | tr ',' ' '); do \
	    case $$n in @) fqdn=$$domain;; *) fqdn=$$n.$$domain;; esac; \
	    printf "%-30s %s\n" "$$fqdn" "$$(dig +short "$$fqdn" @1.1.1.1 | head -1)"; \
	  done

records: ## Every A record DigitalOcean holds for the zone (asks the API; Touch ID)
	@$(OP) sh -c 'domain=$$(sed -n "s/^DOMAIN=//p" ../homelab.local.env ../homelab.env | head -1); \
	  zone=$$(echo "$$domain" | awk -F. "{print \$$(NF-1)\".\"\$$NF}"); \
	  curl -fsS -H "Authorization: Bearer $$DO_TOKEN" \
	    "https://api.digitalocean.com/v2/domains/$$zone/records?per_page=200" | \
	  python3 -c "import json,sys; [print(\"%-20s %s\" % (r[\"name\"], r[\"data\"])) \
	    for r in sorted(json.load(sys.stdin)[\"domain_records\"], key=lambda r: r[\"name\"]) if r[\"type\"]==\"A\"]"'
