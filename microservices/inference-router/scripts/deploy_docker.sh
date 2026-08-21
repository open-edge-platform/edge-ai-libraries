#!/bin/bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Deploy the Inference Router with Docker Compose
#
# Usage:
#   bash scripts/deploy_docker.sh [OPTIONS]
#
# By default this deploys the router *and* the web UI. Pass --standalone to
# deploy only the router (no UI).
#
# Options:
#   --port PORT               Router port (default: 8000)
#   --standalone              Deploy the router only, without the web UI
#   --ui-port PORT            UI port (default: 7010; only with the UI)
#
# Environment:
#   IR_BIND_HOST   Interface the router binds to. Standalone default: 127.0.0.1
#                  (local-only). With the UI it defaults to the host LAN IP so
#                  the UI container can reach the router. Export IR_BIND_HOST to
#                  override (e.g. 0.0.0.0 to allow access from other machines).
#   REGISTRY       Docker registry/namespace prefix for both images (default:
#                  empty, i.e. use locally built images). Set e.g. REGISTRY=intel/
#                  to pull prebuilt images from a remote registry instead.
#   TAG            Image tag for both images (default: latest).
#
# With no REGISTRY set the deploy uses the local ${REGISTRY}inference-router:${TAG}
# image (build it first with --build). When REGISTRY is set the image is pulled
# from that registry; a failed pull stops with a hint to re-run with --build.
# The UI image is handled the same way: pulled by default, built with --build.
#
# Options:
#   --verbose                 Enable verbose logging
#   --verbose_full            Enable full verbose logging (requests + responses)
#   --build                   Force a local build instead of pulling the image(s)
#   --down                    Stop and remove the containers
#
# Examples:
#   bash scripts/deploy_docker.sh                       # router + UI
#   bash scripts/deploy_docker.sh --standalone          # router only
#   bash scripts/deploy_docker.sh --port 9000 --verbose
#   bash scripts/deploy_docker.sh --build
#   bash scripts/deploy_docker.sh --down


set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
COMPOSE_STANDALONE="$PROJECT_ROOT/deployment/docker/docker-compose.yml"
COMPOSE_UI="$PROJECT_ROOT/deployment/docker/docker-compose-ui.yml"

# Defaults
ROUTER_PORT="${ROUTER_PORT:-8000}"
UI_PORT="${UI_PORT:-7010}"
# Whether the operator explicitly set IR_BIND_HOST (we honor it in both modes).
# Otherwise the default depends on the mode: loopback for standalone, host LAN
# IP for the UI deployment (resolved below once the mode is known).
IR_BIND_HOST_RAW="${IR_BIND_HOST:-}"
# Image coordinates. Empty REGISTRY -> use locally built images (the default).
# Set REGISTRY (e.g. intel/) to pull prebuilt images from a remote registry.
# The router and UI images share the same REGISTRY prefix and TAG.
REGISTRY="${REGISTRY:-}"
TAG="${TAG:-latest}"
FORCE_BUILD=false
WITH_UI=true
ACTION="up"
GATEWAY_VERBOSE=""
GATEWAY_VERBOSE_FULL=""

USAGE="Usage: bash scripts/deploy_docker.sh [--port PORT] [--standalone] [--ui-port PORT] [--verbose] [--verbose_full] [--build] [--down]"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)
            ROUTER_PORT="$2"; shift 2 ;;
        --ui-port)
            UI_PORT="$2"; shift 2 ;;
        --standalone)
            WITH_UI=false; shift ;;
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
            echo "$USAGE"
            exit 1 ;;
    esac
done

# ---- Select compose file and resolve the router bind host per mode ----
if [ "$WITH_UI" = true ]; then
    COMPOSE_FILE="$COMPOSE_UI"
    # The router runs with network_mode: host while the UI is on a bridge
    # network, so the UI reaches the router via the host's LAN IP. Detect it and
    # bind the router there (unless the operator overrode IR_BIND_HOST).
    HOST_IP="$(ip route get 1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
    : "${HOST_IP:=$(hostname -I 2>/dev/null | awk '{print $1}')}"
    if [ -z "$HOST_IP" ]; then
        echo "Error: could not determine host IP for the UI to reach the router."
        echo "Export IR_BIND_HOST and SERVER_HOST to a reachable address and re-run,"
        echo "or deploy without the UI using --standalone."
        exit 1
    fi
    IR_BIND_HOST="${IR_BIND_HOST_RAW:-$HOST_IP}"
    SERVER_HOST="$HOST_IP"
else
    COMPOSE_FILE="$COMPOSE_STANDALONE"
    # Loopback by default: the router is local-only unless the operator opts in
    # to remote access by exporting IR_BIND_HOST=0.0.0.0 (or a LAN interface).
    IR_BIND_HOST="${IR_BIND_HOST_RAW:-127.0.0.1}"
fi

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
# `docker compose` reads these via ${VAR:-} substitution in the compose file.
export ROUTER_PORT
export IR_BIND_HOST
export GATEWAY_VERBOSE
export GATEWAY_VERBOSE_FULL
export IR_OV_MODEL
# Image reference the compose file interpolates: ${REGISTRY}inference-router:${TAG}
export REGISTRY
export TAG
IMAGE_REF="${REGISTRY}inference-router:${TAG}"
# UI image shares REGISTRY/TAG with the router; the compose file interpolates
# ${REGISTRY}inference-router-ui:${TAG} the same way.
UI_IMAGE_REF="${REGISTRY}inference-router-ui:${TAG}"
export UI_PORT
export SERVER_HOST
# Proxy settings are forwarded into the container by the compose file.
export http_proxy https_proxy no_proxy

# ---- Print summary ----
echo ""
echo "Starting Inference Router"
echo "========================="
echo "  Compose file:     $COMPOSE_FILE"
echo "  Image:            $IMAGE_REF"
echo "  Bind host:        $IR_BIND_HOST"
echo "  Port:             $ROUTER_PORT"
[ "$IR_BIND_HOST" = "0.0.0.0" ] && echo "  Access:           EXPOSED to all interfaces (remote access enabled)"
echo "  OV model:         $IR_OV_MODEL"
echo "  OV device:        $IR_DEVICE"
[ -n "$GATEWAY_VERBOSE" ]           && echo "  Verbose:          enabled"
[ -n "$GATEWAY_VERBOSE_FULL" ]      && echo "  Verbose full:     enabled"
if [ "$WITH_UI" = true ]; then
    echo "  UI image:         $UI_IMAGE_REF"
    echo "  UI port:          $UI_PORT"
    echo "  UI -> router:     http://$SERVER_HOST:$ROUTER_PORT"
else
    echo "  UI:               disabled (--standalone)"
fi
echo ""

# ---- Obtain the image: pull, or build when --build is passed ----
# build_docker.sh reads IMAGE_NAME/IMAGE_TAG so the local build is tagged with the
# same reference the compose file expects.
build_image() {
    echo "Building image with scripts/build_docker.sh..."
    IMAGE_NAME="${REGISTRY}inference-router" IMAGE_TAG="$TAG" \
        bash "$SCRIPT_DIR/build_docker.sh"
}

# Build the UI image via compose (its build context/args live in the compose
# file). Compose tags it with ${UI_IMAGE}, exported above.
build_ui_image() {
    echo "Building UI image: $UI_IMAGE_REF"
    "${COMPOSE[@]}" build inference-router-ui
}

if [ "$FORCE_BUILD" = true ]; then
    build_image
elif [ -n "$REGISTRY" ]; then
    # Remote registry configured: pull the prebuilt image.
    echo "Pulling image: $IMAGE_REF"
    if ! docker pull "$IMAGE_REF"; then
        echo "Error: failed to pull $IMAGE_REF"
        echo "Re-run with --build to build the image from source instead."
        exit 1
    fi
    echo "Pulled $IMAGE_REF"
else
    # No registry set: use the locally built image.
    if ! docker image inspect "$IMAGE_REF" >/dev/null 2>&1; then
        echo "Error: local image $IMAGE_REF not found."
        echo "Build it first with:            bash $0 --build"
        echo "Or pull a prebuilt image with:  export REGISTRY=intel/ && bash $0"
        exit 1
    fi
    echo "Using local image: $IMAGE_REF"
fi

# ---- Obtain the UI image: same policy as the router image ----
if [ "$WITH_UI" = true ]; then
    if [ "$FORCE_BUILD" = true ]; then
        build_ui_image
    elif [ -n "$REGISTRY" ]; then
        # Remote registry configured: pull the prebuilt UI image.
        echo "Pulling UI image: $UI_IMAGE_REF"
        if ! docker pull "$UI_IMAGE_REF"; then
            echo "Error: failed to pull $UI_IMAGE_REF"
            echo "Re-run with --build to build the UI image from source instead."
            exit 1
        fi
        echo "Pulled $UI_IMAGE_REF"
    else
        # No registry set: use the locally built UI image.
        if ! docker image inspect "$UI_IMAGE_REF" >/dev/null 2>&1; then
            echo "Error: local UI image $UI_IMAGE_REF not found."
            echo "Build it first with:            bash $0 --build"
            echo "Or pull a prebuilt image with:  export REGISTRY=intel/ && bash $0"
            exit 1
        fi
        echo "Using local UI image: $UI_IMAGE_REF"
    fi
fi

# ---- Run ----
"${COMPOSE[@]}" up -d

echo "Router started: http://$IR_BIND_HOST:$ROUTER_PORT"
if [ "$WITH_UI" = true ]; then
    echo "UI started:     http://$SERVER_HOST:$UI_PORT"
fi
echo "Logs:   ${COMPOSE[*]} logs -f router"
echo "Stop:   bash $0 --down"
