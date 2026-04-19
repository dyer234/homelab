#!/bin/sh
# One-time migration: copy Jenkins data from the named Docker volume to the bind mount.
# Run this BEFORE starting Jenkins with the updated docker-compose.yml.
#
# Usage: ./migrate.sh

set -e

DEST="$(dirname "$0")/data"

if [ -d "$DEST" ] && [ "$(ls -A "$DEST" 2>/dev/null)" ]; then
  echo "Error: $DEST already exists and is not empty. Aborting to avoid overwriting data."
  exit 1
fi

if ! docker inspect jenkins_data > /dev/null 2>&1 && ! docker volume inspect jenkins_jenkins_data > /dev/null 2>&1; then
  echo "Error: No jenkins_data or jenkins_jenkins_data volume found."
  exit 1
fi

# Determine the correct volume name
if docker volume inspect jenkins_jenkins_data > /dev/null 2>&1; then
  VOLUME="jenkins_jenkins_data"
else
  VOLUME="jenkins_data"
fi

echo "Migrating data from volume '$VOLUME' to $DEST ..."
mkdir -p "$DEST"

docker run --rm \
  -v "$VOLUME":/source:ro \
  -v "$DEST":/dest \
  alpine sh -c 'cp -a /source/. /dest/'

echo "Migration complete. You can now start Jenkins with the updated docker-compose.yml."
echo "Once verified, remove the old volume with: docker volume rm $VOLUME"
