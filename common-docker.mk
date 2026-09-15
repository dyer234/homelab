# Shared targets for the docker compose apps in this tree.
# Each app's Makefile is `include ../common-docker.mk`, optionally followed by
# app-specific targets (see tailscale/Makefile).
#
# Variables, lowest to highest precedence (see ../homelab.env for the why):
#   ../homelab.env         committed, shared by every app (DOMAIN, TZ, PUID...)
#   ../homelab.local.env   gitignored per-host overrides, if present
#   .env                   gitignored escape hatch, if present (normally absent)
#   process environment    shell exports and whatever `op run` resolves
# Compose stops auto-loading .env once given any --env-file, so it is listed.
#
# App config: each app carries a committed 1pass.env holding its secrets as op://
# REFERENCES, not values (same pattern as infra/*/1pass.env; see common-tofu.mk)
# and its non-secret config in the clear. If that file exists, `up` runs under
# `op run` so the references resolve into the process environment, which compose
# reads for ${VAR} interpolation. Apps with nothing to configure have no file.
# Only `up` and `build` go through `op run`; every other target calls compose
# directly so it never triggers a Touch ID prompt for a value it does not read
# (compose may warn that a variable is unset — harmless).
#
# Overlays, mirroring scripts/up.sh:
#   docker-compose.linux.yml    added automatically on a Linux host
#   docker-compose.no-acme.yml  added when NO_ACME=true, taken from
#                               ../homelab.local.env unless set on the command line
#
# Run `make` with no arguments for the target list.

COMPOSE_FILES := -f docker-compose.yml
ifeq ($(shell uname),Linux)
  ifneq ($(wildcard docker-compose.linux.yml),)
    COMPOSE_FILES += -f docker-compose.linux.yml
  endif
endif
NO_ACME ?= $(shell sed -n 's/^NO_ACME=//p' ../homelab.local.env 2>/dev/null)
ifeq ($(NO_ACME),true)
  ifneq ($(wildcard docker-compose.no-acme.yml),)
    COMPOSE_FILES += -f docker-compose.no-acme.yml
  endif
endif

ENV_FILES := --env-file ../homelab.env
ifneq ($(wildcard ../homelab.local.env),)
  ENV_FILES += --env-file ../homelab.local.env
endif
ifneq ($(wildcard .env),)
  ENV_FILES += --env-file .env
endif

COMPOSE ?= docker compose $(ENV_FILES) $(COMPOSE_FILES)
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
