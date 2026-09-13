include ../docker-common.mk

.PHONY: status routes

status: ## Tailnet status as seen from inside the container
	$(COMPOSE) exec tailscale tailscale status

routes: ## Show advertised routes and whether they are approved
	$(COMPOSE) exec tailscale tailscale status --json | \
	  python3 -c 'import json,sys; s=json.load(sys.stdin)["Self"]; \
	    print("advertised:", s.get("AllowedIPs") or []); \
	    print("approved:  ", s.get("PrimaryRoutes") or [])'
