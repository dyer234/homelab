include ../../common-tofu.mk

.PHONY: policy

# echo | console rather than a <<< herestring: make runs recipes under /bin/sh,
# which has no herestrings, and the failure is a bare syntax error.
policy: ## Render the policy without applying it
	@echo 'local.policy' | $(OP) $(TOFU) console
