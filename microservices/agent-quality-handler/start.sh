#!/usr/bin/env bash
#
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="$(basename -- "${PROJECT_DIR}")"

# Deployment configuration. Update these defaults for the target environment.
# Values already present in the environment take precedence.
: "${REGISTRY:=intel/}"
: "${TAG:=latest}"

: "${STORAGE_SERVICE_URL:=http://host.docker.internal:5001}"
: "${STORAGE_CONNECT_TIMEOUT_SECONDS:=3}"
: "${STORAGE_READ_TIMEOUT_SECONDS:=10}"
: "${STORAGE_READ_MAX_ATTEMPTS:=3}"
: "${STORAGE_RETRY_BACKOFF_SECONDS:=0.25}"

: "${LLM_MODE:=llm}"
: "${LLM_BASE_URL:=http://aqh-ovms:8010/v3}"
: "${LLM_MODEL_NAME:=Qwen/Qwen2.5-3B-Instruct}"
: "${LLM_DEVICE:=CPU}"
: "${LLM_PRECISION:=int8}"
: "${LLM_API_KEY:=UNUSED}"

: "${MQTT_DISABLED:=false}"
: "${MQTT_HOST:=mqtt-broker}"
: "${MQTT_PORT:=1883}"
: "${MQTT_BATCH_TOPIC:=apm/batch-complete}"
: "${MQTT_QOS:=1}"
: "${MQTT_KEEPALIVE:=60}"
: "${MQTT_MAX_PAYLOAD_BYTES:=1048576}"
: "${MQTT_BATCH_CLIENT_ID:=agent-quality-handler-batch}"
: "${MQTT_USERNAME:=}"
: "${MQTT_PASSWORD:=}"

: "${RUN_RETENTION_SECONDS:=86400}"
: "${MAX_RETAINED_RUNS:=1000}"
: "${LOG_LEVEL:=INFO}"

: "${USE_CASE_CONFIGS_DIR:=${PROJECT_DIR}/defaults/config}"
: "${USE_CASE_PROMPTS_DIR:=${PROJECT_DIR}/defaults/prompts}"
: "${USE_CASE_MODELS_DIR:=aqh_model_cache}"

: "${AGENT_PORT:=5002}"
: "${LLM_PORT:=8010}"
: "${MODEL_DOWNLOAD_PORT:=8200}"
: "${MOCK_STORAGE_PORT:=5001}"

: "${OVMS_TAG:=2026.2.1-gpu}"
: "${MODEL_DOWNLOAD_URL:=http://model-download:8000}"
: "${MODEL_DOWNLOAD_TIMEOUT_SECONDS:=3600}"
: "${MODEL_DOWNLOAD_PLUGINS:=huggingface,openvino}"
: "${USER_GROUP_ID:=$(id -g)}"
: "${COMPOSE_PROFILES:=}"

: "${http_proxy:=}"
: "${https_proxy:=}"
: "${no_proxy:=}"

# Supply credentials through the calling environment or a secret manager.
: "${HUGGINGFACEHUB_API_TOKEN:=}"

export REGISTRY TAG
export STORAGE_SERVICE_URL STORAGE_CONNECT_TIMEOUT_SECONDS
export STORAGE_READ_TIMEOUT_SECONDS STORAGE_READ_MAX_ATTEMPTS
export STORAGE_RETRY_BACKOFF_SECONDS
export LLM_MODE LLM_BASE_URL LLM_MODEL_NAME LLM_DEVICE LLM_PRECISION LLM_API_KEY
export MQTT_DISABLED MQTT_HOST MQTT_PORT MQTT_BATCH_TOPIC MQTT_QOS
export MQTT_KEEPALIVE MQTT_MAX_PAYLOAD_BYTES MQTT_BATCH_CLIENT_ID
export MQTT_USERNAME MQTT_PASSWORD
export RUN_RETENTION_SECONDS MAX_RETAINED_RUNS LOG_LEVEL
export USE_CASE_CONFIGS_DIR USE_CASE_PROMPTS_DIR USE_CASE_MODELS_DIR
export AGENT_PORT LLM_PORT MODEL_DOWNLOAD_PORT MOCK_STORAGE_PORT
export OVMS_TAG MODEL_DOWNLOAD_URL MODEL_DOWNLOAD_TIMEOUT_SECONDS
export MODEL_DOWNLOAD_PLUGINS USER_GROUP_ID COMPOSE_PROFILES
export HUGGINGFACEHUB_API_TOKEN
export http_proxy https_proxy no_proxy

if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required but was not found in PATH" >&2
    exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 is required" >&2
    exit 1
fi

compose() {
    docker compose \
        --project-name "${PROJECT_NAME}" \
        -f "${PROJECT_DIR}/docker/compose.yaml" \
        "$@"
}

usage() {
    cat <<'EOF'
Usage:
  ./start.sh [start] [docker compose up options]
  ./start.sh down
  ./start.sh clean
  ./start.sh help

Actions:
  start  Build or start the application in the background (default).
  down   Stop and remove application containers and networks.
  clean  Stop the application and remove containers, networks, and named volumes.
  help   Show this help.

Examples:
  ./start.sh
  ./start.sh --build
  COMPOSE_PROFILES=dev STORAGE_SERVICE_URL=http://mock-storage:5001 ./start.sh --build
  ./start.sh down
  ./start.sh clean
EOF
}

action="${1:-start}"
case "${action}" in
    start)
        if (($# > 0)); then
            shift
        fi
        compose up -d "$@"
        ;;
    down)
        shift
        if (($# > 0)); then
            echo "down does not accept additional arguments" >&2
            usage >&2
            exit 2
        fi
        compose --profile "*" down --remove-orphans
        ;;
    clean)
        shift
        if (($# > 0)); then
            echo "clean does not accept additional arguments" >&2
            usage >&2
            exit 2
        fi
        compose --profile "*" down --volumes --remove-orphans
        ;;
    help|-h|--help)
        usage
        ;;
    -*)
        compose up -d "$@"
        ;;
    *)
        echo "unknown action: ${action}" >&2
        usage >&2
        exit 2
        ;;
esac
