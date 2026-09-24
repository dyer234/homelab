include ../common-docker.mk

.PHONY: run list restore

run: ## Run a backup now (does not disturb the cron schedule)
	$(COMPOSE) exec backups /bin/sh /opt/backup/backup.sh --once

list: ## List what is in the B2 bucket, newest last
	$(COMPOSE) exec backups rclone lsl "b2:$$B2_BUCKET" --config /opt/backup/rclone.conf

restore: ## Restore the newest backup over the local stacks (prompts first)
	@bash restore.sh
