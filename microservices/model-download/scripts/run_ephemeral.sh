#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# =============================================================================
# Ephemeral Model Download Script
#
# Runs the model download service temporarily, performs a single download
# (and optional OpenVINO conversion), then exits. Designed for use inside
# a Docker container in one-shot mode.
#
# Usage:
#   /opt/scripts/run_ephemeral.sh --model-name <name> --hub <hub> [options]
#
# Example:
#   /opt/scripts/run_ephemeral.sh \
#       --model-name meta-llama/Llama-2-7b-hf \
#       --hub huggingface \
#       --is-ovms \
#       --precision int8 \
#       --device CPU
# =============================================================================

set -e

# Color definitions
NC='\033[0m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
CYAN='\033[0;36m'
BOLD='\033[1m'

# Service configuration
SERVICE_HOST="localhost"
SERVICE_PORT=8000
HEALTH_TIMEOUT=120
POLL_INTERVAL=5

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

log_info()    { echo -e "${BLUE}INFO:${NC} $1"; }
log_success() { echo -e "${GREEN}SUCCESS:${NC} $1"; }
log_warning() { echo -e "${YELLOW}WARNING:${NC} $1"; }
log_error()   { echo -e "${RED}ERROR:${NC} $1"; }

show_usage() {
    echo -e "${BOLD}Ephemeral Model Download${NC}"
    echo -e "Run a one-shot model download/conversion and exit.\n"
    echo -e "${BOLD}Usage:${NC} /opt/scripts/run_ephemeral.sh [options]\n"
    echo -e "${BOLD}Required:${NC}"
    echo -e "  ${CYAN}--model-name${NC} <name>       Model identifier (e.g. meta-llama/Llama-2-7b-hf)"
    echo -e "  ${CYAN}--hub${NC} <hub>               Source hub: huggingface, ultralytics, ollama, openvino, geti, hls\n"
    echo -e "${BOLD}Optional:${NC}"
    echo -e "  ${CYAN}--type${NC} <type>             Model type: llm, vlm, embeddings, rerank, vision, 3d-pose, rppg, ai-ecg"
    echo -e "  ${CYAN}--download-path${NC} <path>    Sub-directory under models dir for downloads"
    echo -e "  ${CYAN}--revision${NC} <rev>          Model revision (branch, tag, or commit hash)"
    echo -e "  ${CYAN}--is-ovms${NC}                 Convert to OpenVINO format after downloading"
    echo -e "  ${CYAN}--precision${NC} <prec>        Weight precision for conversion: int4, int8, fp16, fp32 (default: int8)"
    echo -e "  ${CYAN}--device${NC} <dev>            Target device for conversion: CPU, GPU, NPU (default: CPU)"
    echo -e "  ${CYAN}--cache-size${NC} <gb>         KV cache size in GB (for LLM/VLM conversion)"
    echo -e "  ${CYAN}--config-json${NC} <json>      Additional config as JSON string"
    echo -e "  ${CYAN}--help${NC}                    Show this help message"
}

cleanup() {
    if [ -n "$SERVICE_PID" ] && kill -0 "$SERVICE_PID" 2>/dev/null; then
        log_info "Stopping background service (PID: $SERVICE_PID)..."
        kill "$SERVICE_PID" 2>/dev/null || true
        wait "$SERVICE_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
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
        --help)
            show_usage; exit 0 ;;
        *)
            log_error "Unknown option: $1"
            show_usage; exit 1 ;;
    esac
done

# Validate required arguments
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

# Banner
echo -e "${CYAN}========================================================${NC}"
echo -e "${CYAN}  Model Download Service — Ephemeral Mode${NC}"
echo -e "${CYAN}========================================================${NC}"
log_info "Model:     ${BOLD}$MODEL_NAME${NC}"
log_info "Hub:       ${BOLD}$HUB${NC}"
[[ -n "$MODEL_TYPE" ]] && log_info "Type:      ${BOLD}$MODEL_TYPE${NC}"
[[ "$IS_OVMS" == true ]] && log_info "Convert:   ${BOLD}OpenVINO ($DEVICE / $PRECISION)${NC}"

# ---- Start the service in the background ----
log_info "Starting service in background..."
cd /opt

# Activate venv if available
if [ -d "/opt/.venv" ]; then
    source /opt/.venv/bin/activate
fi

uvicorn src.api.main:app --host 0.0.0.0 --port "$SERVICE_PORT" &
SERVICE_PID=$!

# ---- Wait for health check ----
log_info "Waiting for service to become ready (timeout: ${HEALTH_TIMEOUT}s)..."
elapsed=0
while [ $elapsed -lt $HEALTH_TIMEOUT ]; do
    if curl -sf "http://${SERVICE_HOST}:${SERVICE_PORT}/health" > /dev/null 2>&1; then
        log_success "Service is ready."
        break
    fi
    sleep 2
    elapsed=$((elapsed + 2))
done

if [ $elapsed -ge $HEALTH_TIMEOUT ]; then
    log_error "Service failed to start within ${HEALTH_TIMEOUT}s."
    exit 1
fi

# ---- Build the JSON request payload ----
# When converting to OpenVINO, the OpenVINO plugin handles the download internally,
# so we set hub=openvino to route the request through the converter pipeline.
REQUEST_HUB="$HUB"
if [[ "$IS_OVMS" == true ]]; then
    REQUEST_HUB="openvino"
fi

MODEL_OBJ="{\"name\": \"$MODEL_NAME\", \"hub\": \"$REQUEST_HUB\", \"is_ovms\": $IS_OVMS"

if [[ -n "$MODEL_TYPE" ]]; then
    MODEL_OBJ="$MODEL_OBJ, \"type\": \"$MODEL_TYPE\""
fi
if [[ -n "$REVISION" ]]; then
    MODEL_OBJ="$MODEL_OBJ, \"revision\": \"$REVISION\""
fi

# Build config object if conversion is requested
if [[ "$IS_OVMS" == true ]]; then
    CONFIG="{\"precision\": \"$PRECISION\", \"device\": \"$DEVICE\""
    if [[ -n "$CACHE_SIZE" ]]; then
        CONFIG="$CONFIG, \"cache_size\": $CACHE_SIZE"
    fi
    # Merge extra config JSON if provided
    if [[ -n "$CONFIG_JSON" ]]; then
        # Strip outer braces from CONFIG_JSON and append
        EXTRA=$(echo "$CONFIG_JSON" | sed 's/^{//;s/}$//')
        CONFIG="$CONFIG, $EXTRA"
    fi
    CONFIG="$CONFIG}"
    MODEL_OBJ="$MODEL_OBJ, \"config\": $CONFIG"
fi

MODEL_OBJ="$MODEL_OBJ}"
PAYLOAD="{\"models\": [$MODEL_OBJ]}"

log_info "Sending download request..."

# URL-encode download_path for query parameter
ENCODED_PATH=$(python3 -c "import urllib.parse; print(urllib.parse.quote('$DOWNLOAD_PATH', safe=''))")

RESPONSE=$(curl -sf -X POST \
    "http://${SERVICE_HOST}:${SERVICE_PORT}/models/download?download_path=${ENCODED_PATH}" \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD")

if [[ $? -ne 0 || -z "$RESPONSE" ]]; then
    log_error "Failed to submit download request."
    log_error "Payload: $PAYLOAD"
    exit 1
fi

# Extract job IDs from response
JOB_IDS=$(echo "$RESPONSE" | python3 -c "import sys,json; data=json.load(sys.stdin); print(' '.join(data.get('job_ids', [])))")

if [[ -z "$JOB_IDS" ]]; then
    log_error "No job IDs returned. Response: $RESPONSE"
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
        JOB_STATUS=$(curl -sf "http://${SERVICE_HOST}:${SERVICE_PORT}/jobs/$JOB_ID")
        STATUS=$(echo "$JOB_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null)

        case "$STATUS" in
            completed)
                ;;
            failed)
                ERROR=$(echo "$JOB_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('error','Unknown error'))" 2>/dev/null)
                log_error "Job $JOB_ID failed: $ERROR"
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
    # Print output paths
    for JOB_ID in $JOB_IDS; do
        JOB_STATUS=$(curl -sf "http://${SERVICE_HOST}:${SERVICE_PORT}/jobs/$JOB_ID")
        OP_TYPE=$(echo "$JOB_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('operation_type',''))" 2>/dev/null)
        OUTPUT_DIR=$(echo "$JOB_STATUS" | python3 -c "import sys,json; print(json.load(sys.stdin).get('output_dir',''))" 2>/dev/null)
        log_info "$OP_TYPE output: $OUTPUT_DIR"
    done
else
    echo -e "${RED}========================================================${NC}"
    echo -e "${RED}  One or more operations failed${NC}"
    echo -e "${RED}========================================================${NC}"
fi

exit $FINAL_EXIT
