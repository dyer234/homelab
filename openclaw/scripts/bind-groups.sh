#!/usr/bin/env bash
# Route the two WhatsApp groups to their agents:
#
#   tv   -> media (Media Manager)
#   ops  -> ops
#
# The WhatsApp channel has no `channels resolve`, so a group's JID can only be
# learned from a message it actually delivered. Hence three steps:
#
#   scripts/bind-groups.sh open              admit every group, temporarily
#   (send one message in the tv group and one in the ops group)
#   scripts/bind-groups.sh seen              list the JIDs that arrived
#   scripts/bind-groups.sh set <tv> <ops>    lock down to those two
#
# `set` writes the final posture: groupPolicy "open" (every member of an
# admitted group may talk to the bot, no per-number allowlist), a groups map
# holding only those two JIDs with requireMention false (so the bot answers
# every message, and no other group is admitted), the two peer bindings, and
# no catch-all binding. The number is public, so DMs are off unless DM_ALLOW
# names specific numbers:
#
#   DM_ALLOW="+34600000000,+34600000001" scripts/bind-groups.sh set <tv> <ops>
set -euo pipefail

CONTAINER=${CONTAINER:-openclaw}
oc() { docker exec "$CONTAINER" node dist/index.js "$@"; }

case "${1:-}" in
open)
  # "*" admits every group (and answers without an @-mention) so the first
  # message from each lands its JID in a session key. DMs stay off throughout.
  oc config set --batch-json '[
    {"path":"channels.whatsapp.dmPolicy","value":"disabled"},
    {"path":"channels.whatsapp.groupPolicy","value":"open"},
    {"path":"channels.whatsapp.groups","value":{"*":{"requireMention":false}}},
    {"path":"bindings","value":[]}
  ]'
  echo
  echo "Every group is admitted for now, and DMs stay disabled."
  echo "Send one message in the tv group and one in the ops group, then:"
  echo "  make groups-seen"
  ;;

seen)
  echo "Group JIDs this gateway has received messages from:"
  oc sessions list --all-agents --json 2>/dev/null |
    grep -oE '"key": "agent:[^"]*whatsapp:group:[0-9]+@g\.us"' |
    grep -oE '[0-9]+@g\.us' | sort -u | sed 's/^/  /'
  echo
  echo "Recent group traffic (subject, if the channel reported one):"
  oc channels logs --channel whatsapp --lines 400 2>/dev/null |
    grep -iE "g\.us|subject" | tail -15 | sed 's/^/  /' || true
  echo
  echo "Then: make groups TV_JID=<tv>@g.us OPS_JID=<ops>@g.us"
  ;;

set)
  TV_JID=${2:-${TV_JID:-}}
  OPS_JID=${3:-${OPS_JID:-}}
  if [ -z "$TV_JID" ] || [ -z "$OPS_JID" ]; then
    echo "usage: $0 set <tv-jid> <ops-jid>   (or TV_JID=.. OPS_JID=.. make groups)" >&2
    exit 1
  fi
  DM_ALLOW=${DM_ALLOW:-}
  if [ -n "$DM_ALLOW" ]; then
    dm_policy=allowlist
    dm_from=$(printf '%s' "$DM_ALLOW" | awk -F, '{for(i=1;i<=NF;i++){gsub(/^ +| +$/,"",$i); printf "%s\"%s\"", (i>1?",":""), $i}}')
    echo "DMs: allowlist [$DM_ALLOW] -> media"
  else
    dm_policy=disabled
    dm_from=""
    echo "DMs: disabled (groups only)"
  fi
  oc config set --batch-json "$(cat <<JSON
[
  {"path":"channels.whatsapp.dmPolicy","value":"$dm_policy"},
  {"path":"channels.whatsapp.allowFrom","value":[$dm_from]},
  {"path":"channels.whatsapp.groupPolicy","value":"open"},
  {"path":"channels.whatsapp.groups","value":{
     "$TV_JID":{"requireMention":false},
     "$OPS_JID":{"requireMention":false}
  }},
  {"path":"bindings","value":[
    {"agentId":"media","match":{"channel":"whatsapp","peer":{"kind":"group","id":"$TV_JID"}}},
    {"agentId":"ops","match":{"channel":"whatsapp","peer":{"kind":"group","id":"$OPS_JID"}}}
  ]}
]
JSON
)"
  echo
  echo "tv  -> media   $TV_JID"
  echo "ops -> ops     $OPS_JID"
  echo "Mirror both JIDs into openclaw.json5, then: make restart"
  ;;

*)
  echo "usage: $0 open | seen | set <tv-jid> <ops-jid>" >&2
  exit 1
  ;;
esac
