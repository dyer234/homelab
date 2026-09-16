# Shared targets for the OpenTofu modules in this tree.
# Each module's Makefile is a single `include ../../common-tofu.mk`.
#
# Secrets come from 1Password at run time via 1pass.env, which holds op://
# REFERENCES, not values (see README.md, "Secrets"). Targets that need variables
# run under `op run`; the rest call tofu directly so they never trigger a Touch
# ID prompt for values they do not read.
#
# Run `make` with no arguments for the target list.

OP   ?= op run --env-file=1pass.env --
TOFU ?= tofu

# Root domain, resolved the way the compose launchers do it (homelab.local.env
# over homelab.env), exported so scripts run under $(OP) can address homelab
# services by name — e.g. ci-agent/scripts/jenkins_node.py -> https://jenkins.$DOMAIN.
DOMAIN ?= $(shell sed -n 's/^DOMAIN=//p' ../../homelab.local.env ../../homelab.env 2>/dev/null | head -1)
export DOMAIN

# The Docker network this host pins and the Jenkins controller's address on it,
# resolved the same way and exported as TF_VAR_ so the modules derive addresses
# instead of repeating them. Without this, NET_PREFIX lives in homelab.env for
# compose and as a hardcoded literal in every .tf file, and they drift the first
# time a host picks a different /16.
NET_PREFIX ?= $(shell sed -n 's/^NET_PREFIX=//p' ../../homelab.local.env ../../homelab.env 2>/dev/null | head -1)
JENKINS_HOST_SUFFIX ?= $(shell sed -n 's/^JENKINS_HOST_SUFFIX=//p' ../../homelab.local.env ../../homelab.env 2>/dev/null | head -1)
export NET_PREFIX JENKINS_HOST_SUFFIX
TF_VAR_net_prefix ?= $(NET_PREFIX)
TF_VAR_jenkins_host_suffix ?= $(JENKINS_HOST_SUFFIX)
export TF_VAR_net_prefix TF_VAR_jenkins_host_suffix

.DEFAULT_GOAL := help
.PHONY: help init fmt validate plan apply destroy refresh output console

help: ## Show this help
	@grep -hE '^[a-z][a-z-]*:.*?## ' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-9s\033[0m %s\n", $$1, $$2}'

init: ## Download providers (no secrets needed)
	$(TOFU) init -input=false

fmt: ## Rewrite .tf files to canonical format
	$(TOFU) fmt -recursive

validate: ## Check the configuration parses and type-checks
	$(TOFU) validate

plan: ## Show what would change
	$(OP) $(TOFU) plan

apply: ## Create or update the infrastructure
	$(OP) $(TOFU) apply

destroy: ## Tear everything down
	$(OP) $(TOFU) destroy

refresh: ## Reconcile state with reality
	$(OP) $(TOFU) refresh

output: ## Print module outputs
	$(OP) $(TOFU) output

console: ## Interactive expression evaluator
	$(OP) $(TOFU) console
