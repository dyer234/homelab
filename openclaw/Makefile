include ../common-docker.mk

.PHONY: init cli login groups-open groups-seen groups shell doctor

init: ## Create state/ + auth-secrets/ and seed state/openclaw.json (safe to re-run)
	@mkdir -p state auth-secrets && touch state/.gitkeep auth-secrets/.gitkeep
	@if [ -f state/openclaw.json ]; then echo "state/openclaw.json exists, leaving it"; \
	else cp openclaw.json5 state/openclaw.json && echo "seeded state/openclaw.json"; fi

# The CLI shares the gateway's network namespace and needs the gateway token,
# hence `op run`. Interactive by design (QR codes, prompts).
cli: ## Run an openclaw CLI command: make cli ARGS="channels list"
	$(OP) $(COMPOSE) run --rm openclaw-cli $(ARGS)

# Interactive sign-ins go straight into the running gateway: `compose run`
# under `op run` loses the TTY that the OAuth flow needs, and the gateway
# container already holds OPENCLAW_GATEWAY_TOKEN.
login: ## Sign in to a model provider, e.g. make login PROVIDER=openai
	docker exec -it openclaw node dist/index.js models auth login --provider $(or $(PROVIDER),openai)

groups-open: ## Step 1: admit all groups so their JIDs can be discovered
	@bash scripts/bind-groups.sh open

groups-seen: ## Step 2: list group JIDs that have messaged the bot
	@bash scripts/bind-groups.sh seen

groups: ## Step 3: lock in routing: make groups TV_JID=..@g.us OPS_JID=..@g.us
	@bash scripts/bind-groups.sh set "$(TV_JID)" "$(OPS_JID)"

shell: ## Shell inside the running gateway container
	$(COMPOSE) exec openclaw sh

doctor: ## OpenClaw self-check against the mounted state
	$(OP) $(COMPOSE) run --rm openclaw-cli doctor
