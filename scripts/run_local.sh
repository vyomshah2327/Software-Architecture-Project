#!/usr/bin/env bash
# Run the platform as plain processes, with no Docker. Needs PostgreSQL and Redis already running.
#   DATABASE_URL=postgresql://... REDIS_URL=redis://localhost:6379/0 scripts/run_local.sh start|stop|status
# Without RabbitMQ the services skip events but everything else works.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"; RUN="$ROOT/.run"
export REGISTRY_KEY="${REGISTRY_KEY:-local-key}" ALLOW_LOCAL_URLS=true
export REGISTRY_URLS="http://localhost:8000,http://localhost:8001"
SERVICES=(price_history performance volatility_risk indicators fund_builder portfolio correlation_svc alerts_monitor)

# launch NAME DIR COMMAND...   starts the command in DIR and records its real process id
launch() {
  local name=$1 dir=$2; shift 2
  ( cd "$ROOT/$dir" && exec "$@" ) >"$RUN/$name.log" 2>&1 &
  echo $! >"$RUN/$name.pid"
}

case "${1:-start}" in
  start)
    mkdir -p "$RUN"
    launch registry-primary registry uvicorn registry.main:app --port 8000
    launch registry-backup registry uvicorn registry.main:app --port 8001
    port=8101
    for s in "${SERVICES[@]}"; do
      SERVICE_URL="http://localhost:$port" launch "$s" services uvicorn "$s.main:app" --port "$port"
      port=$((port + 1))
    done
    PORT=8080 launch ui ui node src/server.js
    echo "started. UI on http://localhost:8080, logs in $RUN/" ;;
  stop)
    for f in "$RUN"/*.pid; do [ -e "$f" ] && { kill "$(cat "$f")" 2>/dev/null || true; rm -f "$f"; }; done
    echo stopped ;;
  status)
    for f in "$RUN"/*.pid; do
      [ -e "$f" ] && { kill -0 "$(cat "$f")" 2>/dev/null && echo "up   $(basename "$f" .pid)" || echo "down $(basename "$f" .pid)"; }
    done ;;
esac
