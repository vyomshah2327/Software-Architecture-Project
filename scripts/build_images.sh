#!/usr/bin/env bash
# Build (and optionally push) every image. Needs Docker.
#   IMAGE_PREFIX=ghcr.io/vyomshah2327 TAG=latest scripts/build_images.sh [--push]
set -euo pipefail
cd "$(dirname "$0")/.."
PREFIX="${IMAGE_PREFIX:?set IMAGE_PREFIX, for example ghcr.io/vyomshah2327}"
TAG="${TAG:-latest}"
NAME="${NAME_PREFIX:-stock}"
PUSH="${1:-}"

build() {  # image-name dockerfile [build-arg]
  local ref="$PREFIX/$NAME-$1:$TAG"
  echo "== $ref"
  docker build -f "$2" ${3:+--build-arg "$3"} -t "$ref" .
  [ "$PUSH" = "--push" ] && docker push "$ref"
  return 0
}

build registry registry/Dockerfile
build ui ui/Dockerfile
build ingestor ingestor/Dockerfile
build db-init db/Dockerfile
build price-history services/Dockerfile SERVICE=price_history
build performance services/Dockerfile SERVICE=performance
build volatility-risk services/Dockerfile SERVICE=volatility_risk
build indicators services/Dockerfile SERVICE=indicators
build fund-builder services/Dockerfile SERVICE=fund_builder
build portfolio services/Dockerfile SERVICE=portfolio
build correlation services/Dockerfile SERVICE=correlation_svc
build alerts-monitor services/Dockerfile SERVICE=alerts_monitor
