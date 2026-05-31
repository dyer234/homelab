#!/bin/sh
set -eu

: "${DO_TOKEN:?must be set}"
: "${DOMAIN:?must be set}"
: "${RECORD_NAMES:?must be set (comma-separated, e.g. @,*)}"
INTERVAL="${INTERVAL:-300}"
IP_SERVICE="${IP_SERVICE:-https://api.ipify.org}"

API="https://api.digitalocean.com/v2"
AUTH="Authorization: Bearer ${DO_TOKEN}"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*"; }

update_once() {
  ip="$(curl -fsS --max-time 10 "${IP_SERVICE}")"
  case "${ip}" in
    *.*.*.*) ;;
    *) log "invalid IP from ${IP_SERVICE}: ${ip}"; return 1 ;;
  esac

  records_json="$(curl -fsS -H "${AUTH}" "${API}/domains/${DOMAIN}/records?per_page=200")"

  echo "${RECORD_NAMES}" | tr ',' '\n' | while IFS= read -r name; do
    [ -z "${name}" ] && continue
    entry="$(echo "${records_json}" | jq -c --arg n "${name}" '.domain_records[] | select(.type=="A" and .name==$n)')"
    if [ -z "${entry}" ]; then
      log "no A record found for name='${name}' in ${DOMAIN}, skipping"
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
        "${API}/domains/${DOMAIN}/records/${id}" >/dev/null
    fi
  done
}

log "starting DO DDNS for ${DOMAIN} records=${RECORD_NAMES} interval=${INTERVAL}s"
while true; do
  if ! update_once; then
    log "update cycle failed, will retry"
  fi
  sleep "${INTERVAL}"
done
