#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

set -u

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "${PWD}/setup.sh" ] && [ -d "${PWD}/docker" ]; then
    APP_ROOT="${PWD}"
elif [ -n "${VSS_APP_ROOT:-}" ] && [ -f "${VSS_APP_ROOT}/setup.sh" ] && [ -d "${VSS_APP_ROOT}/docker" ]; then
    APP_ROOT="$(cd "${VSS_APP_ROOT}" && pwd)"
else
    APP_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
fi

if [ ! -f "${APP_ROOT}/setup.sh" ] || [ ! -d "${APP_ROOT}/docker" ]; then
    echo "ERROR: Could not resolve the VSS application root. Run this script from APP_ROOT or set VSS_APP_ROOT." >&2
    exit 1
fi
cd "${APP_ROOT}" || exit 1

section() {
    echo -e "\n${BLUE}================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================================================${NC}"
}

run_cmd() {
    echo -e "${GRAY}$*${NC}"
    "$@" 2>&1 || echo -e "${YELLOW}Command failed: $*${NC}"
}

compose_args=(
    -f docker/compose.base.yaml
    -f docker/compose.summary.yaml
    -f docker/compose.vllm.yaml
    -f docker/compose.vllm.xpu.yaml
    -f docker/compose.gpu_ovms.yaml
    -f docker/compose.search.yaml
    -f docker/compose.search.vdms.yaml
    -f docker/compose.search.milvus.yaml
    -f docker/compose.ui.yaml
    -f docker/compose.metrics-manager.yaml
    --profile ovms
    --profile vlm-ov
    --profile vllm
    --profile vllm-xpu
    --profile dual_ui
    --profile singleton_unified_ui
    --profile singleton_summary_ui
    --profile singleton_search_ui
)

services=(
    nginx
    pipeline-manager
    postgres-service
    minio-service
    ovms-service
    vllm-cpu-service
    vllm-xpu-service
    video-ingestion
    audio-analyzer
    rabbitmq-service
    video-search
    vdms-vector-db
    multimodal-dataprep
    vector-retriever
    multimodal-embedding-serving
    metrics-manager
)

find_container_ids() {
    local service="$1"
    local ids=""

    ids="$(docker compose "${compose_args[@]}" ps -q "$service" 2>/dev/null || true)"
    if [ -n "$ids" ]; then
        echo "$ids"
        return 0
    fi

    docker ps -a --filter "name=${service}" --format '{{.ID}}' 2>/dev/null || true
}

section "VSS app root"
echo "${APP_ROOT}"

section "Docker Compose service status"
if ! docker compose "${compose_args[@]}" ps -a 2>&1; then
    echo -e "${YELLOW}Compose status failed, falling back to docker ps name filters.${NC}"
    for svc in "${services[@]}"; do
        docker ps -a --filter "name=${svc}" --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
    done
fi

section "Recent logs for key services"
for svc in "${services[@]}"; do
    echo -e "\n${GREEN}--- ${svc} (last 80 lines) ---${NC}"
    ids="$(find_container_ids "$svc")"
    if [ -z "$ids" ]; then
        echo "No container found for ${svc}."
        continue
    fi
    while IFS= read -r cid; do
        [ -z "$cid" ] && continue
        echo -e "${GRAY}docker logs --tail 80 ${cid}${NC}"
        docker logs --tail 80 "$cid" 2>&1 || echo -e "${YELLOW}Unable to read logs for ${cid}.${NC}"
    done <<< "$ids"
done

section "Health endpoint curls"
declare -a health_checks=(
    "pipeline-manager|http://localhost:${PM_HOST_PORT:-3001}/health"
    "video-search|http://localhost:${VS_HOST_PORT:-7890}/health"
    "ovms-service|http://localhost:${OVMS_HTTP_HOST_PORT:-8300}/v2/health/ready"
    "vllm-cpu-service|http://localhost:${VLLM_HOST_PORT:-8200}/health"
    "video-ingestion|http://localhost:${EVAM_PIPELINE_HOST_PORT:-8090}/pipelines"
    "audio-analyzer|http://localhost:${AUDIO_HOST_PORT:-8999}/api/v1/health"
    "multimodal-dataprep|http://localhost:${MM_DATAPREP_HOST_PORT:-6016}/v1/dataprep/health"
    "vector-retriever|http://localhost:${VECTOR_RETRIEVER_HOST_PORT:-6008}/ready"
    "multimodal-embedding-serving|http://localhost:${EMBEDDING_SERVER_PORT:-9777}/health"
)

for item in "${health_checks[@]}"; do
    name="${item%%|*}"
    url="${item#*|}"
    echo -e "\n${GREEN}${name}: ${url}${NC}"
    curl -fsS --max-time 5 "$url" 2>&1 || echo -e "${YELLOW}Unreachable or unhealthy: ${url}${NC}"
done

section "Documented host port checks"
declare -a ports=(
    "12345|nginx/UI APP_HOST_PORT"
    "3001|pipeline-manager PM_HOST_PORT"
    "7890|video-search VS_HOST_PORT"
    "8300|OVMS REST OVMS_HTTP_HOST_PORT"
    "9300|OVMS gRPC OVMS_GRPC_HOST_PORT"
    "8200|vLLM VLLM_HOST_PORT"
    "8090|DLStreamer EVAM EVAM_PIPELINE_HOST_PORT"
    "8999|audio-analyzer AUDIO_HOST_PORT"
    "5672|RabbitMQ AMQP"
    "15672|RabbitMQ management UI"
    "1883|RabbitMQ MQTT"
    "4001|MinIO API"
    "4002|MinIO console"
    "5432|Postgres"
    "55555|VDMS vector DB"
    "6016|multimodal-dataprep"
    "6008|vector-retriever"
    "9777|multimodal-embedding-serving"
    "9273|vss-collector telemetry"
    "8640|model-download REST (transient)"
)

if command -v ss >/dev/null 2>&1; then
    ss_output="$(ss -ltnp 2>/dev/null || true)"
    for item in "${ports[@]}"; do
        port="${item%%|*}"
        label="${item#*|}"
        echo -e "\n${GREEN}${port} (${label})${NC}"
        matches="$(printf '%s\n' "$ss_output" | awk -v p=":${port}" '$4 ~ p"$" {print}')"
        if [ -n "$matches" ]; then
            printf '%s\n' "$matches"
        else
            echo "No listener found."
        fi
    done
else
    echo -e "${YELLOW}ss is not available; skipping port listener details.${NC}"
fi

section "GPU/NPU visibility"
if command -v lspci >/dev/null 2>&1; then
    echo -e "${GREEN}Intel VGA/Display devices:${NC}"
    lspci | grep -Ei 'vga|display|intel' || true
else
    echo "lspci not found."
fi

echo -e "\n${GREEN}/dev/dri:${NC}"
ls -l /dev/dri 2>&1 || true

echo -e "\n${GREEN}/dev/accel/accel0:${NC}"
ls -l /dev/accel/accel0 2>&1 || true

section "OVMS model config"
if [ -f ov_models/ovms/config.json ]; then
    sed -n '1,160p' ov_models/ovms/config.json
else
    echo "ov_models/ovms/config.json not found."
fi

section "Recent model-download failure log"
model_download_log="$(ls -1t ov_models/model-download-*.log 2>/dev/null | head -n 1 || true)"
if [ -n "$model_download_log" ]; then
    echo "$model_download_log"
    tail -n 80 "$model_download_log"
else
    echo "No persisted model-download failure log found."
fi

section "Setup environment variables commonly required"
for var in \
    MINIO_ROOT_USER MINIO_ROOT_PASSWORD POSTGRES_USER POSTGRES_PASSWORD \
    RABBITMQ_USER RABBITMQ_PASSWORD VLM_MODEL_NAME OVMS_LLM_MODEL_NAME \
    ENABLED_WHISPER_MODELS OD_MODEL_NAME MULTIMODAL_EMBEDDING_MODEL \
    TEXT_EMBEDDING_MODEL ENABLE_VLLM ENABLE_VLLM_GPU \
    VLM_TARGET_DEVICE LLM_TARGET_DEVICE \
    PM_SUMMARIZATION_MAX_COMPLETION_TOKENS OVMS_CACHE_SIZE_GB \
    VECTORDB_BACKEND DATAPREP_EMBEDDING_DEVICE \
    DATAPREP_DETECTION_DEVICE MME_EMBEDDING_DEVICE \
    MODEL_DOWNLOAD_IMAGE MODEL_DOWNLOAD_OVMS_TAG \
    MODEL_DOWNLOAD_HOST_PORT MODEL_DOWNLOAD_JOB_TIMEOUT; do
    if [ -n "${!var+x}" ]; then
        if [[ "$var" == *PASSWORD* || "$var" == *TOKEN* ]]; then
            echo "${var}=<set>"
        else
            echo "${var}=${!var}"
        fi
    else
        echo "${var}=<unset>"
    fi
done

section "Done"
echo "Read-only triage complete. Review the first unhealthy dependency and its logs before changing configuration."
