#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -e 

# Audio Analyzer Docker Setup Script

# Define color codes
RED='\033[0;31m'
NC='\033[0m'

# Default values
BUILD_ONLY=false
DEV_MODE=false
DOWN_CONTAINERS=false
DOCKER_DIR="$(dirname "$0")/docker"

# Display help information
show_help() {
  echo "Audio Analyzer Docker Setup Script"
  echo ""
  echo "Usage: $0 [options]"
  echo ""
  echo "Options:"
  echo "  (no options)          Build and run production environment"
  echo "  --dev                 Build and run development environment"
  echo "  --build               Only build production Docker images"
  echo "  --build-dev           Only build development Docker image"
  echo "  --down                Stop and remove all containers, networks, and volumes"
  echo "  -h, --help            Show this help message"
  echo ""
  echo "Examples:"
  echo "  $0                    Build and run production environment"
  echo "  $0 --dev              Build and run development environment"
  echo "  $0 --build            Build production Docker image only"
  echo "  $0 --build-dev        Build development Docker image only"
  echo "  $0 --down             Stop and remove all containers"
  echo ""
}

# Parse command-line arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev)
      DEV_MODE=true
      shift
      ;;
    --build)
      BUILD_ONLY=true
      shift
      ;;
    --build-dev)
      BUILD_ONLY=true
      DEV_MODE=true
      shift
      ;;
    --down)
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

echo "==== Audio Analyzer Docker Image Build ===="

# If REGISTRY_URL is set, ensure it ends with a trailing slash
[[ -n "$REGISTRY_URL" ]] && REGISTRY_URL="${REGISTRY_URL%/}/"

# If PROJECT_NAME is set, ensure it ends with a trailing slash
[[ -n "$PROJECT_NAME" ]] && PROJECT_NAME="${PROJECT_NAME%/}/"

export REGISTRY="${REGISTRY_URL}${PROJECT_NAME}"
echo "Using Registry : ${REGISTRY}"

# Set up Docker compose command and environment based on mode
if [ "$DEV_MODE" = true ]; then
  ENVIRONMENT="dev"
  TAG="${TAG:-latest}-dev"
  echo "Setting up $ENVIRONMENT environment..."
else
  ENVIRONMENT="prod"
  echo "Setting up $ENVIRONMENT environment..."
fi

if [ "$BUILD_ONLY" = true ]; then
    docker build -f "$DOCKER_DIR/Dockerfile" --target $ENVIRONMENT -t "${REGISTRY}audio-analyzer:${TAG:-latest}" .
    echo "Docker image built for $ENVIRONMENT environment with tag: ${REGISTRY}audio-analyzer:${TAG:-latest}"
    echo "==== Build complete! ===="
    exit 0
fi

echo "==== Audio Analyzer Docker Setup ===="

export STORAGE_BACKEND=${STORAGE_BACKEND:-minio}
export ENABLED_WHISPER_MODELS=${ENABLED_WHISPER_MODELS}
export DEFAULT_DEVICE=${DEFAULT_DEVICE:-"cpu"}
export MAX_FILE_SIZE=${MAX_FILE_SIZE:-"314572800"}  # 300MB by default
export USE_FP16=${USE_FP16:-"true"}

# Determine MinIO service YAML inclusion based on storage backend
MINIO_COMPOSE_FILE=""
if [ "$STORAGE_BACKEND" = "minio" ]; then
  MINIO_COMPOSE_FILE="-f $DOCKER_DIR/compose-minio.yaml"
fi

# Set docker-compose command based on environment and storage backend
DOCKER_COMPOSE_COMMAND="docker compose -f $DOCKER_DIR/compose.yaml $MINIO_COMPOSE_FILE"
if [ "$DEV_MODE" = true ]; then
  DOCKER_COMPOSE_COMMAND="$DOCKER_COMPOSE_COMMAND -f $DOCKER_DIR/compose.dev.yaml"
fi

# Handle container shutdown
if [ "$DOWN_CONTAINERS" = true ]; then
  echo "Stopping and removing containers..."
  $DOCKER_COMPOSE_COMMAND down
  echo "==== Containers stopped and removed! ===="
  exit 0
fi

# Only check MinIO credentials if we're not just stopping containers
if [ "$DOWN_CONTAINERS" = false ] && [ "$STORAGE_BACKEND" = "minio" ]; then
  if [ -z "$MINIO_ACCESS_KEY" ]; then
    echo -e "${RED}ERROR: MINIO_ACCESS_KEY is not set in environment.${NC}"
    exit 1
  fi

  if [ -z "$MINIO_SECRET_KEY" ]; then
    echo -e "${RED}ERROR: MINIO_SECRET_KEY is not set in environment.${NC}"
    exit 1
  fi

  if [ -z "$ENABLED_WHISPER_MODELS" ]; then
    echo -e "${RED}ERROR: No models specified. Please set ENABLED_WHISPER_MODELS environment variable.${NC}"
    exit 1
  fi
fi


# Display configuration for build or run operations
echo "Configuration:"
echo "- IMAGE REGISTRY: $REGISTRY"
echo "- ENABLED_WHISPER_MODELS: $ENABLED_WHISPER_MODELS"
echo "- DEFAULT_WHISPER_MODEL: $DEFAULT_WHISPER_MODEL"
echo "- DEFAULT_DEVICE: $DEFAULT_DEVICE"
echo "- STORAGE_BACKEND: $STORAGE_BACKEND"
echo "- MAX_FILE_SIZE: $MAX_FILE_SIZE bytes"
echo "- USE_FP16: $USE_FP16"
echo "- MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY:0:3}*****" # Show first 3 characters for security
echo "- MINIO_SECRET_KEY: ${MINIO_SECRET_KEY:0:3}*****" # Show first 3 characters for security

# Run the container if not build-only
if [ "$BUILD_ONLY" = false ]; then
  echo "Starting containers..."
  $DOCKER_COMPOSE_COMMAND up -d
  
  echo "==== Setup complete! ===="
  echo "Audio Analyzer service is running at http://localhost:8000/api/v1"
  echo "API documentation available at http://localhost:8000/docs"
  
  if [ "$STORAGE_BACKEND" = "minio" ]; then
    echo "MinIO console is available at http://localhost:9001"
    echo "  Username: ${MINIO_ACCESS_KEY:0:3}*****"
    echo "  Password: ${MINIO_SECRET_KEY:0:3}*****"
  fi
  echo "To stop the service: $0 --down"
else
  echo "==== Build complete! ===="
fi