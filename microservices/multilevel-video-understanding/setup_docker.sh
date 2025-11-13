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
DOCKER_DIR="$(dirname "$0")/docker"

# Display help information
show_help() {
  echo "Multi-level Video Understanding Docker Setup Script"
  echo ""
  echo "Usage: $0 [options]"
  echo ""
  echo "Options:"
  echo "  --prod                Create and start production containers only"
  echo "  --build               Build production Docker image only"
  echo "  --build-prod          Build and then run production Docker images"
  echo "  --down                Stop and remove all containers, networks, and volumes"
  echo "  -h, --help            Show this help message"
  echo ""
  echo "Examples:"
  echo "  $0                    Create and start production containers only"
  echo "  $0 --prod             Create and start production containers only"
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
    echo "Starting containers for $ENVIRONMENT environment..."
    $DOCKER_CMD up -d
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
