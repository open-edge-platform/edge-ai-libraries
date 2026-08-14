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
#
# Environment:
#   IR_BIND_HOST   Interface the router binds to (default: 127.0.0.1, local-only).
#                  Export IR_BIND_HOST=0.0.0.0 to allow access from other machines.
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
# Loopback by default: the router is local-only unless the operator opts in to
# remote access by exporting IR_BIND_HOST=0.0.0.0 (or a specific LAN interface).
IR_BIND_HOST="${IR_BIND_HOST:-127.0.0.1}"
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

export IR_DEVICE="${IR_DEVICE:-GPU}"
if [[ "$IR_DEVICE" == GPU* && -e /dev/dri ]]; then
    export IR_RENDER_DEVICE=/dev/dri
    # Resolve the host `render` group GID so the container can open /dev/dri/renderD*.
    RENDER_GROUP_ID="$(getent group render 2>/dev/null | cut -d: -f3)"
    : "${RENDER_GROUP_ID:=993}"
    export RENDER_GROUP_ID
else
    if [[ "$IR_DEVICE" == GPU* ]]; then
        echo "IR_DEVICE=$IR_DEVICE but /dev/dri not found on host -> classifier will fall back to CPU"
    fi
    export IR_RENDER_DEVICE=/dev/null
fi

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

if [ -z "${IR_OV_MODEL:-}" ]; then
    echo "Please export the OpenVINO classifier model directory on this host first:"
    echo "  export IR_OV_MODEL=/opt/models/Qwen3.5-2B-FP16"
    exit 1
fi

# Seed workspace with rsd policy/strategy defaults if the operator hasn't
# provided overrides. The rsd module prefers workspace copies and falls back
# to the bundled files under src/rsd, so this just surfaces them for editing.
mkdir -p "$PROJECT_ROOT/workspace"
for yaml_file in policy.yaml strategy.yaml; do
    if [ ! -f "$PROJECT_ROOT/workspace/$yaml_file" ]; then
        echo "workspace/$yaml_file not found; copying default from src/rsd"
        cp "$PROJECT_ROOT/src/rsd/$yaml_file" "$PROJECT_ROOT/workspace/$yaml_file"
    fi
done

mkdir -p "$PROJECT_ROOT/workspace/logs"

# ---- Export environment for docker compose ----
# `docker compose` reads these via ${VAR:-} substitution in docker-compose.yml.
export ROUTER_PORT
export IR_BIND_HOST
export GATEWAY_VERBOSE
export GATEWAY_VERBOSE_FULL
export IR_OV_MODEL
# Proxy settings are forwarded into the container by docker-compose.yml.
export http_proxy https_proxy no_proxy

# ---- Print summary ----
echo ""
echo "Starting Inference Router"
echo "========================="
echo "  Compose file:     $COMPOSE_FILE"
echo "  Bind host:        $IR_BIND_HOST"
echo "  Port:             $ROUTER_PORT"
[ "$IR_BIND_HOST" = "0.0.0.0" ] && echo "  Access:           EXPOSED to all interfaces (remote access enabled)"
echo "  OV model:         $IR_OV_MODEL"
echo "  OV device:        $IR_DEVICE"
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

echo "Router started: http://$IR_BIND_HOST:$ROUTER_PORT"
echo "Logs:   ${COMPOSE[*]} logs -f router"
echo "Stop:   bash $0 --down"
