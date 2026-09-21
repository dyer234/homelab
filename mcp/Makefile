include ../common-docker.mk

.PHONY: register token servers

register: ## Sync gateways, REST tools and virtual servers from catalog/ (idempotent)
	@python3 register.py

token: ## Mint a 7-day admin bearer token (only needed if AUTH_REQUIRED is turned back on)
	@$(COMPOSE) exec contextforge sh -c \
	  'python3 -m mcpgateway.utils.create_jwt_token --username "$$PLATFORM_ADMIN_EMAIL" --exp 10080 --secret "$$JWT_SECRET_KEY"'

servers: ## Status of the stdio sidecar and the servers it is serving
	@$(COMPOSE) exec mcp-stdio python3 -c \
	  'import json,urllib.request; print(json.dumps(json.load(urllib.request.urlopen("http://localhost:8096/status")), indent=2))'
