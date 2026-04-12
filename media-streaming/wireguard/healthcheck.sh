#!/bin/sh

INTERFACE="wg0"
MAX_AGE=180  # seconds

log() {
  echo "[healthcheck][wireguard] $1"
}

fail() {
  echo "[healthcheck][wireguard][FAIL] $1" >&2
  exit 1
}

GRACE=180  # seconds after container start to allow "no handshake yet"
UPTIME=$(cut -d. -f1 /proc/uptime)

if [ "$UPTIME" -lt "$GRACE" ]; then
  echo "[healthcheck][wireguard] Warming up (${UPTIME}s < ${GRACE}s); not failing yet"
  exit 0
fi

# Ensure wg exists
if ! wg show "$INTERFACE" >/dev/null 2>&1; then
  fail "Interface $INTERFACE not found"
fi

NOW=$(date +%s)

LAST_HANDSHAKE=$(wg show "$INTERFACE" latest-handshakes | awk '{print $2}')

if [ -z "$LAST_HANDSHAKE" ] || [ "$LAST_HANDSHAKE" = "0" ]; then
  fail "No successful handshake yet"
fi

AGE=$((NOW - LAST_HANDSHAKE))

if [ "$AGE" -gt "$MAX_AGE" ]; then
  fail "Handshake too old (${AGE}s > ${MAX_AGE}s)"
fi

log "OK (last handshake ${AGE}s ago)"
exit 0
