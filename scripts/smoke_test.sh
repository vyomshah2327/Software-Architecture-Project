#!/usr/bin/env bash
# Checks a running deployment. Usage: scripts/smoke_test.sh <ui-url> [registry-primary-url] [registry-backup-url]
# Waits up to 3 minutes for all eight services to appear in the registry.
set -uo pipefail
UI="${1:?usage: smoke_test.sh <ui-url> [primary] [backup]}"; UI="${UI%/}"
PRIMARY="${2:-}"; BACKUP="${3:-}"
fail=0
ok()   { echo "ok   $*"; }
bad()  { echo "FAIL $*"; fail=1; }

curl -fsS -m 10 "$UI/health" >/dev/null && ok "UI is up" || bad "UI health"
for r in "$PRIMARY" "$BACKUP"; do
  [ -n "$r" ] && { curl -fsS -m 10 "${r%/}/health" >/dev/null && ok "registry $r healthy" || bad "registry $r"; }
done

count=0
for _ in $(seq 1 36); do
  count=$(curl -fsS -m 10 "$UI/api/search" 2>/dev/null | python3 -c "import sys,json; print(len(json.load(sys.stdin)['services']))" 2>/dev/null || echo 0)
  [ "$count" -ge 8 ] && break
  sleep 5
done
[ "$count" -ge 8 ] && ok "all $count services registered and healthy" || bad "only $count of 8 services found"

curl -fsS -m 10 "$UI/api/search?q=risk" | grep -q volatility-risk && ok "search finds the risk tool" || bad "search for risk"

for url in $(curl -fsS -m 10 "$UI/api/search" | python3 -c "import sys,json; [print(s['url']) for s in json.load(sys.stdin)['services']]"); do
  id=$(curl -fsS -m 10 -D - -o /dev/null "$url/health" | tr -d '\r' | awk -F': ' 'tolower($1)=="x-instance-id"{print $2}')
  [ -n "$id" ] && ok "$url answered as instance $id" || bad "$url gave no instance id"
done
exit $fail
