#!/bin/sh
set -eu

: "${DO_TOKEN:?must be set}"
: "${DOMAIN:?must be set}"
: "${RECORD_NAMES:?must be set (comma-separated, e.g. @,*)}"
INTERVAL="${INTERVAL:-300}"
IP_SERVICE="${IP_SERVICE:-https://api.ipify.org}"
# Status for the Homepage card, served by busybox httpd (see docker-compose.yml).
STATUS_FILE="${STATUS_FILE:-/srv/status.json}"

API="https://api.digitalocean.com/v2"
AUTH="Authorization: Bearer ${DO_TOKEN}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# Carried across cycles so the card can show when a record last actually moved.
last_change="never"
last_change_epoch=""
public_ip="-"
records="-"

# "never" or "3h ago" — Homepage's relativeDate can't render "never", so the
# text is built here and refreshed on every write.
ago() {
  [ -n "${last_change_epoch}" ] || { echo "never"; return; }
  s=$(( $(date +%s) - last_change_epoch ))
  if [ "$s" -lt 3600 ]; then echo "$(( s / 60 ))m ago"
  elif [ "$s" -lt 86400 ]; then echo "$(( s / 3600 ))h ago"
  else echo "$(( s / 86400 ))d ago"; fi
}

# write_status STATUS — snapshot the last cycle as JSON, atomically so the
# card never reads a half-written file.
write_status() {
  mkdir -p "$(dirname "${STATUS_FILE}")"
  jq -n --arg status "$1" --arg ip "${public_ip}" --arg records "${records}" \
        --arg domain "${DOMAIN}" --arg check "$(now)" \
        --arg change "${last_change}" --arg change_ago "$(ago)" \
    '{status: $status, public_ip: $ip, records: $records, domain: $domain,
      last_check: $check, last_change: $change, last_change_ago: $change_ago}' \
    > "${STATUS_FILE}.tmp" && mv "${STATUS_FILE}.tmp" "${STATUS_FILE}"
}

# fail MESSAGE — log it and publish it on the card. Callers `return 1` after
# it: set -e is suspended inside a function called from `if`, so a bare
# non-zero status here would not stop the cycle.
fail() { log "$1"; write_status "Error: $1"; }

update_once() {
  ip="$(curl -fsS --max-time 10 "${IP_SERVICE}")" || { fail "could not get public IP from ${IP_SERVICE}"; return 1; }
  case "${ip}" in
    *.*.*.*) ;;
    *) fail "invalid IP from ${IP_SERVICE}: ${ip}"; return 1 ;;
  esac
  public_ip="${ip}"

  records_json="$(curl -fsS -H "${AUTH}" "${API}/domains/${DOMAIN}/records?per_page=200")" \
    || { fail "DigitalOcean API rejected lookup of ${DOMAIN} (is the zone there?)"; return 1; }

  # Per-record results, collected in the parent shell: "name=IP" pairs for the
  # card, plus whether anything changed this cycle.
  summary=""
  changed=false
  for name in $(echo "${RECORD_NAMES}" | tr ',' ' '); do
    entry="$(echo "${records_json}" | jq -c --arg n "${name}" '.domain_records[] | select(.type=="A" and .name==$n)')"
    if [ -z "${entry}" ]; then
      log "no A record found for name='${name}' in ${DOMAIN}, skipping"
      summary="${summary}${summary:+, }${name}=missing"
      continue
    fi
    id="$(echo "${entry}" | jq -r '.id')"
    current="$(echo "${entry}" | jq -r '.data')"
    if [ "${current}" = "${ip}" ]; then
      log "${name}.${DOMAIN} already ${ip}"
    else
      log "updating ${name}.${DOMAIN}: ${current} -> ${ip}"
      curl -fsS -X PATCH -H "${AUTH}" -H "Content-Type: application/json" \
        -d "{\"data\":\"${ip}\"}" \
        "${API}/domains/${DOMAIN}/records/${id}" >/dev/null \
        || { fail "PATCH of ${name}.${DOMAIN} failed"; return 1; }
      changed=true
    fi
    summary="${summary}${summary:+, }${name}=${ip}"
  done
  records="${summary}"

  if [ "${changed}" = true ]; then
    last_change="$(now)"
    last_change_epoch="$(date +%s)"
    write_status "Updated"
  else
    write_status "In sync"
  fi
}

log "starting DO DDNS for ${DOMAIN} records=${RECORD_NAMES} interval=${INTERVAL}s"
write_status "Starting"
while true; do
  if ! update_once; then
    log "update cycle failed, will retry"
  fi
  sleep "${INTERVAL}"
done
