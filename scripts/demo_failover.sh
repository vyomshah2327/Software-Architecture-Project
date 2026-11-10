#!/usr/bin/env bash
# Stops the primary registry, shows search still works through the backup, then brings it back.
# Works with the processes from run_local.sh. For compose use: docker compose stop registry-primary
set -euo pipefail
cd "$(dirname "$0")/.."; RUN="$(pwd)/.run"
UI="${UI:-http://localhost:8080}"
show() { curl -s -m 5 "$UI/api/search?q=$1" | python3 -c "import sys,json; j=json.load(sys.stdin); print('   registry:', j.get('role','down'), '| tools found:', len(j.get('services',[])))"; }
echo "1. normal"; show ""
echo "2. stopping the primary registry"; kill "$(cat $RUN/registry-primary.pid)"; start=$(date +%s)
until curl -s -m 5 "$UI/api/search" | grep -q '"backup"'; do sleep 0.5; done
echo "   backup answering after $(( $(date +%s) - start )) s"; show ""
echo "3. starting the primary again"
( cd registry && exec uvicorn registry.main:app --port 8000 ) >"$RUN/registry-primary.log" 2>&1 &
echo $! >"$RUN/registry-primary.pid"
sleep 12; show ""
