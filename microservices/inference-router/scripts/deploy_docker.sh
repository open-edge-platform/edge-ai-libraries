#!/bin/bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Deploy the Inference Router with Docker Compose
#
# Usage:
#   bash scripts/deploy_docker.sh [OPTIONS]
#
# Options:
#   --port PORT               Router port (default: 8000)
#   --verbose                 Enable verbose logging
#   --verbose_full            Enable full verbose logging (requests + responses)
#   --build                   Build the Docker image with scripts/build_docker.sh
#   --down                    Stop and remove the router container
#
# Examples:
#   bash scripts/deploy_docker.sh
#   bash scripts/deploy_docker.sh --port 9000 --verbose
#   bash scripts/deploy_docker.sh --build
#   bash scripts/deploy_docker.sh --down


set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_FILE="$PROJECT_ROOT/deployment/docker/docker-compose.yml"

# Defaults
ROUTER_PORT="${ROUTER_PORT:-8000}"
FORCE_BUILD=false
ACTION="up"
GATEWAY_VERBOSE=""
GATEWAY_VERBOSE_FULL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)
            ROUTER_PORT="$2"; shift 2 ;;
        --verbose)
            GATEWAY_VERBOSE=1; shift ;;
        --verbose_full)
            GATEWAY_VERBOSE=1; GATEWAY_VERBOSE_FULL=1; shift ;;
        --build)
            FORCE_BUILD=true; shift ;;
        --down)
            ACTION="down"; shift ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: bash scripts/deploy_docker.sh [--port PORT] [--verbose] [--verbose_full] [--build] [--down]"
            exit 1 ;;
    esac
done

# Pick a `docker compose` command (v2 plugin or legacy v1 binary).
if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
else
    echo "Error: 'docker compose' or 'docker-compose' not found"
    exit 1
fi

COMPOSE+=(-f "$COMPOSE_FILE")

# ---- Stop ----
if [ "$ACTION" = "down" ]; then
    echo "Stopping router..."
    "${COMPOSE[@]}" down
    echo "Router stopped."
    exit 0
fi

# ---- Pre-flight checks ----
if [ ! -f "$PROJECT_ROOT/workspace/config.yaml" ]; then
    echo "Error: config.yaml not found in workspace ($PROJECT_ROOT/workspace)"
    echo "Copy the template first:  cp config.example.yaml workspace/config.yaml"
    exit 1
fi
mkdir -p "$PROJECT_ROOT/workspace/logs"

# ---- Export environment for docker compose ----
# `docker compose` reads these via ${VAR:-} substitution in docker-compose.yml.
export ROUTER_PORT
export GATEWAY_VERBOSE
export GATEWAY_VERBOSE_FULL
# Proxy settings are forwarded into the container by docker-compose.yml.
export http_proxy https_proxy no_proxy

# ---- Print summary ----
echo ""
echo "Starting Inference Router"
echo "========================="
echo "  Compose file:     $COMPOSE_FILE"
echo "  Port:             $ROUTER_PORT"
[ -n "$GATEWAY_VERBOSE" ]           && echo "  Verbose:          enabled"
[ -n "$GATEWAY_VERBOSE_FULL" ]      && echo "  Verbose full:     enabled"
echo ""

# ---- Build (optional) ----
if [ "$FORCE_BUILD" = true ]; then
    echo "Building image with scripts/build_docker.sh..."
    bash "$SCRIPT_DIR/build_docker.sh"
fi

# ---- Run ----
"${COMPOSE[@]}" up -d

echo "Router started: http://0.0.0.0:$ROUTER_PORT"
echo "Logs:   ${COMPOSE[*]} logs -f router"
echo "Stop:   bash $0 --down"
