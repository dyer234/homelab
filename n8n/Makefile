include ../common-docker.mk

.PHONY: webhooks

# Runs on media_net (the *arr apps are not reachable from the host by name),
# with each app's API key read out of its own config.xml at call time.
# The workflow must be imported and ACTIVE first: both apps test the URL
# before saving the connection.
webhooks: ## Point Sonarr and Radarr at the arr-download-watch workflow
	@SONARR_API_KEY=$$(python3 -c "import xml.etree.ElementTree as E; print(E.parse('../media-streaming/config/sonarr/config.xml').getroot().findtext('ApiKey'))"); \
	 RADARR_API_KEY=$$(python3 -c "import xml.etree.ElementTree as E; print(E.parse('../media-streaming/config/radarr/config.xml').getroot().findtext('ApiKey'))"); \
	 docker run --rm --network media-streaming_media_net \
	   -e SONARR_API_KEY="$$SONARR_API_KEY" -e RADARR_API_KEY="$$RADARR_API_KEY" \
	   -v "$$PWD/scripts:/scripts:ro" python:3.13-alpine python /scripts/register-arr-webhooks.py
