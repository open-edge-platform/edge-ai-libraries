#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e 

# Multi-level Video Understanding Docker Setup Script

# Service port
SERVICE_PORT=${SERVICE_PORT:-8192}

# Define color codes
RED='\033[0;31m'
NC='\033[0m'

# Default values
BUILD_IMAGE=false
UP_CONTAINERS=true
DOWN_CONTAINERS=false
LIGHT_MODE=false
DOCKER_DIR="$(dirname "$0")/docker"
VLLM_SERVICE_PORT=${VLLM_SERVICE_PORT:-41091}

# Decide whether we manage the bundled on-device serving or the user has pointed
# the microservice at an external / remote OpenAI-compatible serving. This is
# driven entirely by VLM_BASE_URL / LLM_BASE_URL (falling back to the bundled
# default). Anything that is not the in-network `vllm-ipex-serving` is external.
VLLM_ENDPOINT="${VLM_BASE_URL:-${LLM_BASE_URL:-http://vllm-ipex-serving:8000/v1}}"
case "$VLLM_ENDPOINT" in
  *vllm-ipex-serving*) USE_LOCAL_VLLM=true ;;   # bundled service on app-network
  *)                   USE_LOCAL_VLLM=false ;;  # external / remote serving
esac

# Host-reachable URL for the readiness probe. The in-network name
# `vllm-ipex-serving` is not resolvable from the host, so probe the mapped port;
# a remote endpoint is probed directly at its configured URL.
if [ "$USE_LOCAL_VLLM" = true ]; then
  VLLM_HEALTH_URL="http://localhost:${VLLM_SERVICE_PORT}/v1/models"
else
  VLLM_HEALTH_URL="${VLLM_ENDPOINT%/}/models"
fi

# Returns success if the target serving already answers with a loaded model.
is_vllm_healthy() {
  curl -s --max-time 5 "$VLLM_HEALTH_URL" 2>/dev/null | grep -q '"id"'
}

# Display help information
show_help() {
  echo "Multi-level Video Understanding Docker Setup Script"
  echo ""
  echo "Usage: $0 [options]"
  echo ""
  echo "Options:"
  echo "  --prod                End-to-end: start all services (vllm-ipex-serving + multilevel-video-understanding)"
  echo "  --light               Reuse an existing serving at VLM_BASE_URL/LLM_BASE_URL if healthy; start multilevel only"
  echo "  --build               Build production Docker image only"
  echo "  --build-prod          Build and then run production Docker images"
  echo "  --down                Stop and remove all containers, networks, and volumes"
  echo "  -h, --help            Show this help message"
  echo ""
  echo "Examples:"
  echo "  $0                    End-to-end: start all services (default)"
  echo "  $0 --prod             End-to-end: start all services"
  echo "  $0 --light            Use existing serving: start multilevel only when the serving is already healthy"
  echo "  $0 --build            Build production Docker image only"
  echo "  $0 --build-prod       Build and then run production Docker images"
  echo "  $0 --down             Stop and remove all containers"
  echo ""
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --build-prod)
      BUILD_IMAGE=true
      UP_CONTAINERS=true
      DOWN_CONTAINERS=false
      shift
      ;;
    --build)
      BUILD_IMAGE=true
      UP_CONTAINERS=false
      DOWN_CONTAINERS=false
      shift
      ;;
    --prod)
      BUILD_IMAGE=false
      UP_CONTAINERS=true
      DOWN_CONTAINERS=false
      shift
      ;;
    --light)
      BUILD_IMAGE=false
      UP_CONTAINERS=true
      DOWN_CONTAINERS=false
      LIGHT_MODE=true
      shift
      ;;
    --down)
      BUILD_IMAGE=false
      UP_CONTAINERS=false
      DOWN_CONTAINERS=true
      shift
      ;;
    -h|--help)
      show_help
      exit 0
      ;;
    *)
      echo -e "${RED}Unknown option: $1${NC}"
      show_help
      exit 1
      ;;
  esac
done

echo "==== Multi-level Video Understanding Docker Setup ===="

export PROJECT_NAME=${PROJECT_NAME}

# If REGISTRY_URL is set, ensure it ends with a trailing slash
[[ -n "$REGISTRY_URL" ]] && REGISTRY_URL="${REGISTRY_URL%/}/"

# If PROJECT_NAME is set, ensure it ends with a trailing slash
[[ -n "$PROJECT_NAME" ]] && PROJECT_NAME="${PROJECT_NAME%/}/"

export REGISTRY="${REGISTRY_URL}${PROJECT_NAME}"
echo "Using Registry : ${REGISTRY}"

TARGET_IMAGE_NAME=${REGISTRY:-}multilevel-video-understanding:${TAG:-latest}

cd "$DOCKER_DIR" || { echo -e "${RED}Error: Could not navigate to docker directory!${NC}"; exit 1; }

DOCKER_CMD="docker compose -f compose.yaml"
ENVIRONMENT="production"
echo "Using $ENVIRONMENT environment configuration..."

# Handle docker image build
if [ "$BUILD_IMAGE" = true ]; then
  echo "Building Docker image for $ENVIRONMENT environment (--no-cache)..."
  $DOCKER_CMD build --no-cache
  # echo "Building Docker image for $ENVIRONMENT environment"
  # $DOCKER_CMD build
  echo "==== Build complete! ===="
fi

# Handle container startup
if [ "$UP_CONTAINERS" = true ]; then
  if docker image inspect "$TARGET_IMAGE_NAME" >/dev/null 2>&1; then
    if [ "$LIGHT_MODE" = true ]; then
      # User intent (--light): reuse an already-running model serving at the
      # configured endpoint (VLM_BASE_URL / LLM_BASE_URL) and start only the
      # microservice. Works for a warm local serving OR an external/remote one.
      if is_vllm_healthy; then
        echo "Model serving already healthy at ${VLLM_HEALTH_URL} — starting multilevel-video-understanding only."
        $DOCKER_CMD up -d --no-deps multilevel-video-understanding
      elif [ "$USE_LOCAL_VLLM" = true ]; then
        echo "Local vllm-ipex-serving not healthy yet — starting the full stack instead."
        echo "(first run pulls/compiles the model — this can take 3-20+ min)"
        $DOCKER_CMD up -d
      else
        echo "Warning: external serving not reachable at ${VLLM_HEALTH_URL}; starting multilevel only (it will retry at runtime)."
        $DOCKER_CMD up -d --no-deps multilevel-video-understanding
      fi
    else
      # Default (end-to-end): bring up the bundled serving + microservice together.
      echo "Starting all services for $ENVIRONMENT environment..."
      echo "(first run pulls/compiles the model in vllm-ipex-serving — this can take 3-20+ min)"
      $DOCKER_CMD up -d
    fi
    echo "==== Setup complete! ===="
    echo "Multi-level Video Understanding service is running at http://localhost:${SERVICE_PORT}/v1"
    echo "API documentation available at http://localhost:${SERVICE_PORT}/docs"
    echo "To stop the service: $0 --down"
  else
    echo "Error: $TARGET_IMAGE_NAME not exists!"
    echo "To build the docker image: $0 --build"
    exit 1
  fi
fi

# Handle container shutdown
if [ "$DOWN_CONTAINERS" = true ]; then
  echo "Stopping and removing $ENVIRONMENT containers..."
  $DOCKER_CMD down
  echo "==== Containers stopped and removed! ===="
fi

# Display configuration for build or run operations
echo "Configuration:"
echo "- IMAGE REGISTRY: $REGISTRY"
