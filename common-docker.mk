# Shared targets for the docker compose apps in this tree.
# Each app's Makefile is `include ../common-docker.mk`, optionally followed by
# app-specific targets (see tailscale/Makefile).
#
# Secrets: an app whose credentials live in 1Password carries a committed
# 1pass.env of op:// REFERENCES, not values (same pattern as infra/*/1pass.env; see common-tofu.mk).
# If that file exists, `up` runs under `op run` so the references resolve into
# the process environment, which compose reads for ${VAR} interpolation. If it
# does not, `up` is plain docker compose and the app's .env applies as before.
# Only `up` and `build` go through `op run`; every other target calls compose
# directly so it never triggers a Touch ID prompt for a value it does not read
# (compose may warn that a variable is unset — harmless).
#
# Overlays, mirroring scripts/up.sh:
#   docker-compose.linux.yml    added automatically on a Linux host
#   docker-compose.no-acme.yml  added when NO_ACME=true
#
# Run `make` with no arguments for the target list.

COMPOSE_FILES := -f docker-compose.yml
ifeq ($(shell uname),Linux)
  ifneq ($(wildcard docker-compose.linux.yml),)
    COMPOSE_FILES += -f docker-compose.linux.yml
  endif
endif
ifeq ($(NO_ACME),true)
  ifneq ($(wildcard docker-compose.no-acme.yml),)
    COMPOSE_FILES += -f docker-compose.no-acme.yml
  endif
endif

COMPOSE ?= docker compose $(COMPOSE_FILES)
OP      ?= $(if $(wildcard 1pass.env),op run --env-file=1pass.env --,)

.DEFAULT_GOAL := help
.PHONY: help up down stop restart build pull logs ps config

help: ## Show this help
	@grep -hE '^[a-z][a-z-]*:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-9s\033[0m %s\n", $$1, $$2}'

up: ## Start (or recreate) the app; secrets from 1Password if 1pass.env exists
	$(OP) $(COMPOSE) up -d --remove-orphans

down: ## Stop and remove containers (volumes and bind mounts survive)
	$(COMPOSE) down

stop: ## Stop containers without removing them
	$(COMPOSE) stop

restart: ## Restart containers in place
	$(COMPOSE) restart

build: ## Build images; secrets from 1Password if 1pass.env exists
	$(OP) $(COMPOSE) build

pull: ## Pull images
	$(COMPOSE) pull

logs: ## Follow logs
	$(COMPOSE) logs -f

ps: ## Show container and health status
	$(COMPOSE) ps

config: ## Print the resolved compose file (secrets NOT resolved)
	$(COMPOSE) config
