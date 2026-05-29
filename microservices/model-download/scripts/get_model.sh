#!/bin/bash

# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# If sourced (. or source), re-run as a subprocess so exit won't close the shell
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    bash "${BASH_SOURCE[0]}" "$@"
    return $?
fi

# Color definitions
NC='\033[0m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'

# Execution mode: "host" (docker run) or "internal" (inside container)
EXEC_MODE="host"

# Service configuration
SERVICE_PORT=8000
HEALTH_TIMEOUT=180
POLL_INTERVAL=5
CONTAINER_NAME="model-download-ephemeral"

# Default values
MODEL_NAME=""
HUB=""
MODEL_TYPE=""
DOWNLOAD_PATH=""
REVISION=""
IS_OVMS=false
PRECISION="int8"
DEVICE="CPU"
CACHE_SIZE=""
CONFIG_JSON=""

# Docker defaults (host mode only)
DEFAULT_MODEL_PATH="$PWD/models"
DEFAULT_IMAGE_TAG="latest"
DEFAULT_IMAGE_REGISTRY="intel/"
MODEL_PATH=""
IMAGE_TAG=""
PLUGINS="all"
OVMS_RELEASE_TAG="v2025.4.1"

# Environment variables to pass (host mode)
HF_TOKEN="${HUGGINGFACEHUB_API_TOKEN:-${HF_TOKEN:-}}"
GETI_HOST="${GETI_HOST:-}"
GETI_TOKEN="${GETI_TOKEN:-}"
GETI_WORKSPACE_ID="${GETI_WORKSPACE_ID:-}"

# Error log file
ERROR_LOG_DIR="${PWD}/.model_download_logs"
mkdir -p "$ERROR_LOG_DIR" 2>/dev/null || ERROR_LOG_DIR="/tmp"
ERROR_LOG_FILE="${ERROR_LOG_DIR}/model_download_$(date +%Y%m%d_%H%M%S).log"
HAS_ERROR=false

log_info()    { echo -e "${BLUE}INFO:${NC} $1"; }
log_success() { echo -e "${GREEN}SUCCESS:${NC} $1"; }
log_warning() { echo -e "${YELLOW}WARNING:${NC} $1"; echo "[$(date -Iseconds)] WARNING: $1" >> "$ERROR_LOG_FILE"; }
log_error()   { echo -e "${RED}ERROR:${NC} $1"; echo "[$(date -Iseconds)] ERROR: $1" >> "$ERROR_LOG_FILE"; HAS_ERROR=true; }

# Write context header to log file
write_log_header() {
    {
        echo "===== Model Download Ephemeral Mode - Error Log ====="
        echo "Timestamp: $(date -Iseconds)"
        echo "Mode: $EXEC_MODE"
        if [[ "$EXEC_MODE" == "host" ]]; then
            echo "Image: ${FULL_IMAGE:-not set}"
        fi
        echo "Model Path: ${MODEL_PATH:-not set}"
        echo "Plugins: ${PLUGINS:-not set}"
        echo ""
    } >> "$ERROR_LOG_FILE"
}

# Append container/service logs to error log on failure
write_failure_logs() {
    if [[ "$HAS_ERROR" != true ]]; then
        return
    fi
    if [[ "$EXEC_MODE" == "host" ]]; then
        if docker ps -aq --filter "name=${CONTAINER_NAME}" 2>/dev/null | grep -q .; then
            {
                echo ""
                echo "===== Container Logs ====="
                docker logs "${CONTAINER_NAME}" 2>&1 | tail -100
            } >> "$ERROR_LOG_FILE" 2>/dev/null
        fi
    fi
}

show_usage() {
    echo -e "${BOLD}Ephemeral Model Download${NC}"
    echo -e "Run a one-shot model download/conversion and exit.\n"
    echo -e "${BOLD}Usage:${NC} scripts/get_model.sh [options]\n"
    echo -e "${BOLD}Required:${NC}"
    echo -e "  ${CYAN}--model-name${NC} <name>        Model identifier (e.g. meta-llama/Llama-2-7b-hf)"
    echo -e "  ${CYAN}--hub${NC} <hub>                Source hub: huggingface, ultralytics, ollama, openvino, geti, hls\n"
    echo -e "${BOLD}Model Options:${NC}"
    echo -e "  ${CYAN}--type${NC} <type>              Model type: llm, vlm, embeddings, rerank, vision, 3d-pose, rppg, ai-ecg"
    echo -e "  ${CYAN}--download-path${NC} <path>     Sub-directory under models dir for downloads"
    echo -e "  ${CYAN}--revision${NC} <rev>           Model revision (branch, tag, or commit hash)"
    echo -e "  ${CYAN}--is-ovms${NC}                  Convert to OpenVINO format after downloading"
    echo -e "  ${CYAN}--precision${NC} <prec>         Weight precision: int4, int8, fp16, fp32 (default: int8)"
    echo -e "  ${CYAN}--device${NC} <dev>             Target device: CPU, GPU, NPU (default: CPU)"
    echo -e "  ${CYAN}--cache-size${NC} <gb>          KV cache size in GB (for LLM/VLM conversion)"
    echo -e "  ${CYAN}--config-json${NC} <json>       Additional config as inline JSON string\n"
    echo -e "${BOLD}Docker Options:${NC}"
    echo -e "  ${CYAN}--model-path${NC} <path>        Host path for model storage (default: $DEFAULT_MODEL_PATH)"
    echo -e "  ${CYAN}--image-tag${NC} <tag>          Docker image tag (default: $DEFAULT_IMAGE_TAG)"
    echo -e "  ${CYAN}--plugins${NC} <list>           Comma-separated plugins to enable (default: all)"
    echo -e "  ${CYAN}--ovms-release-tag${NC} <tag>   OVMS release tag (default: $OVMS_RELEASE_TAG)\n"
    echo -e "  ${CYAN}--help${NC}                     Show this help message"
}

# Save original args for log
ORIGINAL_ARGS="$*"

# ---- Cleanup trap ----
cleanup() {
    write_failure_logs

    if [[ "$EXEC_MODE" == "host" ]]; then
        if docker ps -q --filter "name=${CONTAINER_NAME}" 2>/dev/null | grep -q .; then
            log_info "Stopping container ${CONTAINER_NAME}..."
            docker stop "${CONTAINER_NAME}" > /dev/null 2>&1 || true
        fi
        if docker ps -aq --filter "name=${CONTAINER_NAME}" 2>/dev/null | grep -q .; then
            docker rm -f "${CONTAINER_NAME}" > /dev/null 2>&1 || true
        fi
    else
        # Internal mode: stop background uvicorn
        if [[ -n "${SERVICE_PID:-}" ]] && kill -0 "$SERVICE_PID" 2>/dev/null; then
            log_info "Stopping background service (PID: $SERVICE_PID)..."
            kill "$SERVICE_PID" 2>/dev/null || true
            wait "$SERVICE_PID" 2>/dev/null || true
        fi
    fi

    # Only keep the log file if there were errors
    if [[ "$HAS_ERROR" == true ]]; then
        echo -e "${YELLOW}ERROR LOG:${NC} $ERROR_LOG_FILE"
    else
        rm -f "$ERROR_LOG_FILE"
    fi
}
trap cleanup EXIT

# ---- Parse arguments ----
while [[ $# -gt 0 ]]; do
    case "$1" in
        --internal)
            EXEC_MODE="internal"; shift ;;
        --model-name)
            MODEL_NAME="$2"; shift 2 ;;
        --hub)
            HUB="$2"; shift 2 ;;
        --type)
            MODEL_TYPE="$2"; shift 2 ;;
        --download-path)
            DOWNLOAD_PATH="$2"; shift 2 ;;
        --revision)
            REVISION="$2"; shift 2 ;;
        --is-ovms)
            IS_OVMS=true; shift ;;
        --precision)
            PRECISION="$2"; shift 2 ;;
        --device)
            DEVICE="$2"; shift 2 ;;
        --cache-size)
            CACHE_SIZE="$2"; shift 2 ;;
        --config-json)
            CONFIG_JSON="$2"; shift 2 ;;
        --model-path)
            MODEL_PATH="$2"; shift 2 ;;
        --image-tag)
            IMAGE_TAG="$2"; shift 2 ;;
        --plugins)
            PLUGINS="$2"; shift 2 ;;
        --ovms-release-tag)
            OVMS_RELEASE_TAG="$2"; shift 2 ;;
        --help)
            show_usage; exit 0 ;;
        *)
            log_error "Unknown option: $1"
            show_usage; exit 1 ;;
    esac
done

# ---- Validate inputs ----
if [[ -z "$MODEL_NAME" ]]; then
    log_error "--model-name is required"
    show_usage
    exit 1
fi
if [[ -z "$HUB" ]]; then
    log_error "--hub is required"
    show_usage
    exit 1
fi

# =============================================================================
# HOST MODE: Start container via docker run, then interact with it
# =============================================================================
start_service_host() {
    # Set defaults
    if [[ -z "$MODEL_PATH" ]]; then
        MODEL_PATH="$DEFAULT_MODEL_PATH"
    fi
    if [[ "$MODEL_PATH" != /* ]]; then
        MODEL_PATH="$PWD/$MODEL_PATH"
    fi
    if [[ -z "$IMAGE_TAG" ]]; then
        IMAGE_TAG="$DEFAULT_IMAGE_TAG"
    fi

    # Build full image name
    FULL_IMAGE="${DEFAULT_IMAGE_REGISTRY}model-download:${IMAGE_TAG}"

    # Banner
    echo -e "${CYAN}========================================================${NC}"
    echo -e "${CYAN}  Model Download Service — Ephemeral Mode (Docker)${NC}"
    echo -e "${CYAN}========================================================${NC}"
    log_info "Model:     ${BOLD}$MODEL_NAME${NC}"
    log_info "Hub:       ${BOLD}$HUB${NC}"
    [[ -n "$MODEL_TYPE" ]] && log_info "Type:      ${BOLD}$MODEL_TYPE${NC}"
    [[ "$IS_OVMS" == true ]] && log_info "Convert:   ${BOLD}OpenVINO ($DEVICE / $PRECISION)${NC}"
    log_info "Image:     ${BOLD}$FULL_IMAGE${NC}"
    log_info "Models:    ${BOLD}$MODEL_PATH${NC}"
    log_info "Plugins:   ${BOLD}$PLUGINS${NC}"

    # Ensure model path exists
    mkdir -p "$MODEL_PATH"

    # Remove any existing ephemeral container
    if docker ps -aq --filter "name=${CONTAINER_NAME}" 2>/dev/null | grep -q .; then
        log_warning "Removing existing container: ${CONTAINER_NAME}"
        docker rm -f "${CONTAINER_NAME}" > /dev/null 2>&1 || true
    fi

    # Build docker env args
    DOCKER_ENV_ARGS=(
        -e "ENABLED_PLUGINS=${PLUGINS}"
        -e "MODEL_PATH=/opt/models"
        -e "OVMS_RELEASE_TAG=${OVMS_RELEASE_TAG}"
        -e "no_proxy=${no_proxy:-}"
        -e "HF_HUB_ENABLE_HF_TRANSFER=1"
    )
    if [[ -n "$HF_TOKEN" ]]; then
        DOCKER_ENV_ARGS+=(-e "HF_TOKEN=${HF_TOKEN}")
    fi
    if [[ -n "$GETI_HOST" ]]; then
        DOCKER_ENV_ARGS+=(-e "GETI_HOST=${GETI_HOST}")
        DOCKER_ENV_ARGS+=(-e "GETI_TOKEN=${GETI_TOKEN}")
        DOCKER_ENV_ARGS+=(-e "GETI_WORKSPACE_ID=${GETI_WORKSPACE_ID}")
    fi

    # Start the container (detached — docker handles image pull synchronously)
    log_info "Starting container: ${BOLD}${CONTAINER_NAME}${NC} (pulling image if needed)..."

    CONTAINER_ID=$(docker run -d --rm \
        --name "${CONTAINER_NAME}" \
        "${DOCKER_ENV_ARGS[@]}" \
        -v "${MODEL_PATH}:/opt/models" \
        -p "0:${SERVICE_PORT}" \
        --group-add "$(id -g)" \
        "${FULL_IMAGE}" \
        --plugins "${PLUGINS}" 2>&1)

    if [[ $? -ne 0 ]]; then
        log_error "Failed to start container: $CONTAINER_ID"
        exit 1
    fi

    HOST_PORT=$(docker port "${CONTAINER_NAME}" "${SERVICE_PORT}/tcp" 2>/dev/null | head -1 | cut -d: -f2)
    if [[ -z "$HOST_PORT" ]]; then
        log_error "Failed to get mapped port for container."
        docker logs "${CONTAINER_NAME}" 2>&1 | tail -20
        exit 1
    fi

    SERVICE_URL="http://localhost:${HOST_PORT}"
    log_info "Service URL: ${BOLD}${SERVICE_URL}${NC}"
}

# =============================================================================
# INTERNAL MODE: Start uvicorn in background (inside container)
# =============================================================================
start_service_internal() {
    echo -e "${CYAN}========================================================${NC}"
    echo -e "${CYAN}  Model Download Service — Ephemeral Mode (Internal)${NC}"
    echo -e "${CYAN}========================================================${NC}"
    log_info "Model:     ${BOLD}$MODEL_NAME${NC}"
    log_info "Hub:       ${BOLD}$HUB${NC}"
    [[ -n "$MODEL_TYPE" ]] && log_info "Type:      ${BOLD}$MODEL_TYPE${NC}"
    [[ "$IS_OVMS" == true ]] && log_info "Convert:   ${BOLD}OpenVINO ($DEVICE / $PRECISION)${NC}"

    HEALTH_TIMEOUT=120

    log_info "Starting service in background..."
    cd /opt

    # Activate venv if available
    if [ -d "/opt/.venv" ]; then
        source /opt/.venv/bin/activate
    fi

    uvicorn src.api.main:app --host 0.0.0.0 --port "$SERVICE_PORT" &
    SERVICE_PID=$!

    SERVICE_URL="http://localhost:${SERVICE_PORT}"
}

# =============================================================================
# COMMON: Wait for health, build payload, send request, poll
# =============================================================================

# ---- Start service based on mode ----
write_log_header

if [[ "$EXEC_MODE" == "host" ]]; then
    start_service_host
else
    start_service_internal
fi

# ---- Wait for health check ----
log_info "Waiting for service to become ready (timeout: ${HEALTH_TIMEOUT}s)..."
elapsed=0
while [ $elapsed -lt $HEALTH_TIMEOUT ]; do
    if curl -sf "${SERVICE_URL}/health" > /dev/null 2>&1; then
        log_success "Service is ready."
        break
    fi

    if [[ "$EXEC_MODE" == "host" ]]; then
        # Check if container is still running
        if ! docker ps -q --filter "name=${CONTAINER_NAME}" 2>/dev/null | grep -q .; then
            log_error "Container stopped unexpectedly. Logs:"
            docker logs "${CONTAINER_NAME}" 2>&1 | tail -30
            exit 1
        fi
    else
        # Check if uvicorn process is still running
        if ! kill -0 "$SERVICE_PID" 2>/dev/null; then
            log_error "Service process exited unexpectedly."
            exit 1
        fi
    fi

    sleep 3
    elapsed=$((elapsed + 3))
done

if [ $elapsed -ge $HEALTH_TIMEOUT ]; then
    log_error "Service failed to start within ${HEALTH_TIMEOUT}s."
    if [[ "$EXEC_MODE" == "host" ]]; then
        log_error "Container logs:"
        docker logs "${CONTAINER_NAME}" 2>&1 | tail -30
    fi
    exit 1
fi

# ---- Build the JSON request payload ----
IS_OVMS_PY=$([[ "$IS_OVMS" == true ]] && echo "True" || echo "False")

    PAYLOAD=$(python3 << PYEOF
import json

model = {"name": "$MODEL_NAME", "hub": "$HUB", "is_ovms": $IS_OVMS_PY}

model_type = "$MODEL_TYPE"
revision = "$REVISION"
if model_type:
    model["type"] = model_type
if revision:
    model["revision"] = revision

# Build config if OVMS conversion or config-json provided
is_ovms = $IS_OVMS_PY
config_json_str = '''$CONFIG_JSON'''

if is_ovms or config_json_str:
    config = {}
    if is_ovms:
        config["precision"] = "$PRECISION"
        config["device"] = "$DEVICE"
        cache_size = "$CACHE_SIZE"
        if cache_size:
            config["cache_size"] = int(cache_size)
    if config_json_str:
        try:
            extra = json.loads(config_json_str)
            config.update(extra)
        except json.JSONDecodeError:
            pass
    model["config"] = config

payload = {"models": [model]}
print(json.dumps(payload))
PYEOF
)

if [[ $? -ne 0 || -z "$PAYLOAD" ]]; then
    log_error "Failed to build request payload."
    exit 1
fi

log_info "Request payload:"
echo "$PAYLOAD" | python3 -m json.tool 2>/dev/null || echo "$PAYLOAD"
echo ""

# ---- Send download request ----
log_info "Sending download request..."

ENCODED_PATH=""
if [[ -n "$DOWNLOAD_PATH" ]]; then
    ENCODED_PATH=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$DOWNLOAD_PATH', safe=''))")
fi

# Use -w to capture HTTP status code, -s for silent, no -f so we get response body on errors
HTTP_RESPONSE=$(curl -s -w "\n%{http_code}" -X POST \
    "${SERVICE_URL}/models/download?download_path=${ENCODED_PATH}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

# Split response body and HTTP status code
HTTP_STATUS=$(echo "$HTTP_RESPONSE" | tail -1)
RESPONSE=$(echo "$HTTP_RESPONSE" | sed '$d')

if [[ "$HTTP_STATUS" -ge 400 ]] 2>/dev/null; then
    log_error "Download request failed with HTTP $HTTP_STATUS"
    log_error "Response from server:"
    FORMATTED_RESP=$(echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE")
    echo "$FORMATTED_RESP"
    {
        echo ""
        echo "===== Request Details ====="
        echo "URL: ${SERVICE_URL}/models/download?download_path=${ENCODED_PATH}"
        echo "Payload: $PAYLOAD"
        echo ""
        echo "===== Response (HTTP $HTTP_STATUS) ====="
        echo "$FORMATTED_RESP"
    } >> "$ERROR_LOG_FILE"
    exit 1
fi

if [[ -z "$RESPONSE" ]]; then
    log_error "Empty response from server (HTTP $HTTP_STATUS)"
    exit 1
fi

# Extract job IDs from response
JOB_IDS=$(echo "$RESPONSE" | python3 -c "import sys,json; data=json.load(sys.stdin); print(' '.join(data.get('job_ids', [])))" 2>/dev/null)

if [[ -z "$JOB_IDS" ]]; then
    log_error "No job IDs returned."
    log_error "Server response:"
    echo "$RESPONSE" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE"
    exit 1
fi

log_info "Jobs submitted: ${BOLD}$JOB_IDS${NC}"

# ---- Poll job status until all complete or any fails ----
ALL_DONE=false
FINAL_EXIT=0

while [[ "$ALL_DONE" != true ]]; do
    sleep "$POLL_INTERVAL"
    ALL_DONE=true

    for JOB_ID in $JOB_IDS; do
        JOB_STATUS=$(curl -s "${SERVICE_URL}/jobs/$JOB_ID")
        if [[ -z "$JOB_STATUS" ]]; then
            log_warning "Job $JOB_ID: no response from server, retrying..."
            ALL_DONE=false
            continue
        fi
        STATUS=$(echo "$JOB_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null)

        case "$STATUS" in
            completed)
                ;;
            failed)
                ERROR=$(echo "$JOB_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','Unknown error'))" 2>/dev/null)
                log_error "Job $JOB_ID failed: $ERROR"
                {
                    echo ""
                    echo "===== Job Failure: $JOB_ID ====="
                    echo "$JOB_STATUS" | python3 -m json.tool 2>/dev/null || echo "$JOB_STATUS"
                } >> "$ERROR_LOG_FILE"
                FINAL_EXIT=1
                ;;
            queued|downloading|converting)
                log_info "Job $JOB_ID: $STATUS ..."
                ALL_DONE=false
                ;;
            *)
                log_warning "Job $JOB_ID: unexpected status '$STATUS'"
                ALL_DONE=false
                ;;
        esac
    done
done

# ---- Print results ----
echo ""
if [[ $FINAL_EXIT -eq 0 ]]; then
    echo -e "${GREEN}========================================================${NC}"
    echo -e "${GREEN}  All operations completed successfully${NC}"
    echo -e "${GREEN}========================================================${NC}"
    for JOB_ID in $JOB_IDS; do
        JOB_STATUS=$(curl -s "${SERVICE_URL}/jobs/$JOB_ID")
        OP_TYPE=$(echo "$JOB_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('operation_type',''))" 2>/dev/null)
        OUTPUT_DIR=$(echo "$JOB_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('output_dir',''))" 2>/dev/null)
        log_info "$OP_TYPE output: $OUTPUT_DIR"
    done
else
    echo -e "${RED}========================================================${NC}"
    echo -e "${RED}  One or more operations failed${NC}"
    echo -e "${RED}========================================================${NC}"
    HAS_ERROR=true
fi

exit $FINAL_EXIT
