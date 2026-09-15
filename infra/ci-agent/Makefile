include ../../common-tofu.mk

.PHONY: nodes

nodes: ## Jenkins' view of the agents: online/offline, idle/busy, labels
	@$(OP) python3 scripts/jenkins_node.py list
