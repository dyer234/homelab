include ../../common-tofu.mk

.PHONY: nodes devices

# The prefix lives in 1pass.env, which only `op run` reads -- make itself never
# sees TF_VAR_*. Pull it out the same way common-tofu.mk pulls DOMAIN, so the
# listing is filtered to this fleet rather than the whole tailnet.
AGENT_PREFIX ?= $(shell sed -n 's/^TF_VAR_agent_name_prefix=//p' 1pass.env)

nodes: ## Jenkins' view of the agents: online/offline, idle/busy, labels
	@$(OP) python3 scripts/jenkins_node.py list

devices: ## Tailnet's view: registered device records and when each was last seen
	@$(OP) python3 scripts/tailscale_device.py list $(AGENT_PREFIX)
