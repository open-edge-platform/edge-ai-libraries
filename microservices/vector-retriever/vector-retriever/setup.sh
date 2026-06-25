#!/bin/bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

SCRIPT_IS_SOURCED=0
if [[ "${BASH_SOURCE[0]}" != "${0}" ]]; then
    SCRIPT_IS_SOURCED=1
else
    set -e
fi

RED='\033[0;31m'
NC='\033[0m'
BACKENDS=(vdms milvus pgvector faiss)
STACK_VOLUME_NAMES=(vdms-db data-prep milvus-db pgvector-db)

REQUIRED_ENV_MISSING=()

is_sourced() {
    [[ "${SCRIPT_IS_SOURCED}" -eq 1 ]]
}

finish() {
    local code="${1:-0}"
    if is_sourced; then
        return "${code}"
    fi
    exit "${code}"
}

print_usage() {
    echo "Usage:"
    echo "  source ./setup.sh"
    echo "  source ./setup.sh --up-with-vdms"
    echo "  source ./setup.sh --up-with-milvus"
    echo "  source ./setup.sh --up-with-pgvector"
    echo "  source ./setup.sh --up-with-faiss"
    echo "  source ./setup.sh --build"
    echo "  source ./setup.sh --build --backend <name> [--backend <name> ...]"
    echo "  source ./setup.sh --down"
    echo "  source ./setup.sh --clean-data"
    echo "  source ./setup.sh --conf"
    echo "  source ./setup.sh --nosetup"
    echo "  source ./setup.sh --help"
}

run_build_script() {
    local build_script
    build_script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/build.sh"

    if [[ ! -f "${build_script}" ]]; then
        echo -e "${RED}Build helper not found: ${build_script}${NC}" >&2
        return 1
    fi

    if ! bash "${build_script}" "$@"; then
        return 1
    fi
}

require_env_var() {
    local var_name="$1"
    if [[ -z "${!var_name:-}" ]]; then
        REQUIRED_ENV_MISSING+=("$var_name")
    fi
}

validate_required_env_vars() {
    REQUIRED_ENV_MISSING=()

    # Required for all backends.
    require_env_var "EMBEDDING_MODEL_NAME"
    require_env_var "EMBEDDINGS_ENDPOINT"
    require_env_var "INDEX_NAME"

    # Backend-specific required variables.
    case "$RETRIEVER_BACKEND" in
        vdms)
            require_env_var "VDMS_VDB_HOST"
            require_env_var "VDMS_VDB_PORT"
            ;;
        milvus)
            require_env_var "MILVUS_URI"
            ;;
        pgvector)
            require_env_var "PGVECTOR_CONNECTION_STRING"
            ;;
        faiss)
            ;;
    esac

    if [[ ${#REQUIRED_ENV_MISSING[@]} -gt 0 ]]; then
        echo -e "${RED}Missing required environment variable(s):${NC}" >&2
        for var_name in "${REQUIRED_ENV_MISSING[@]}"; do
            echo "  - ${var_name}" >&2
        done
        echo "Set required variables before running setup.sh." >&2
        echo "Example:" >&2
        echo "  export EMBEDDING_MODEL_NAME=<model-name>" >&2
        return 1
    fi
}

down_all_backend_stacks() {
    local down_args=("$@")
    local backend
    for backend in "${BACKENDS[@]}"; do
        docker compose -f docker/compose.yaml -f "docker/compose.${backend}.yaml" down "${down_args[@]}" || true
    done
}

get_compose_project_name() {
    if [[ -n "${COMPOSE_PROJECT_NAME:-}" ]]; then
        echo "${COMPOSE_PROJECT_NAME}"
    else
        basename "$PWD"
    fi
}

remove_stack_named_volumes() {
    local project_name
    local volume_name
    local found=0

    project_name="$(get_compose_project_name)"

    for volume_name in "${STACK_VOLUME_NAMES[@]}"; do
        local full_volume_name="${project_name}_${volume_name}"
        if docker volume inspect "${full_volume_name}" >/dev/null 2>&1; then
            found=1
            docker volume rm "${full_volume_name}" >/dev/null 2>&1 || true
            echo "Removed volume: ${full_volume_name}"
        fi
    done

    if [[ "${found}" -eq 0 ]]; then
        echo "No stack volumes found for project '${project_name}'"
    fi
}

export TAG=${TAG:-latest}
host_ip=$(ip route get 1 | awk '{print $7}')
export HOST_IP=${HOST_IP:-$host_ip}

[[ -n "$REGISTRY_URL" ]] && REGISTRY_URL="${REGISTRY_URL%/}/"
[[ -n "$PROJECT_NAME" ]] && PROJECT_NAME="${PROJECT_NAME%/}/"
export REGISTRY="${REGISTRY_URL}${PROJECT_NAME}"

export VECTOR_RETRIEVER_HOST_PORT=${VECTOR_RETRIEVER_HOST_PORT:-6008}
export VECTOR_RETRIEVER_LOG_LEVEL=${VECTOR_RETRIEVER_LOG_LEVEL:-INFO}
export RETRIEVER_BACKEND=${RETRIEVER_BACKEND:-vdms}

# Allow explicit startup flags to set backend without requiring env export first.
case "$1" in
    --up-with-vdms)
        export RETRIEVER_BACKEND="vdms"
        ;;
    --up-with-milvus)
        export RETRIEVER_BACKEND="milvus"
        ;;
    --up-with-pgvector)
        export RETRIEVER_BACKEND="pgvector"
        ;;
    --up-with-faiss)
        export RETRIEVER_BACKEND="faiss"
        ;;
esac

if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    print_usage
    if is_sourced; then
        return 0
    fi
    exit 0
fi

export VDMS_IMAGE=${VDMS_IMAGE:-intellabs/vdms:v2.12.0}
export MILVUS_IMAGE=${MILVUS_IMAGE:-milvusdb/milvus:v2.6.14}
export PGVECTOR_IMAGE=${PGVECTOR_IMAGE:-pgvector/pgvector:pg18}

export VDMS_VDB_HOST=${VDMS_VDB_HOST:-vdms-vector-db}
export VDMS_VDB_PORT=${VDMS_VDB_PORT:-55555}
export VDMS_VDB_HOST_PORT=${VDMS_VDB_HOST_PORT:-55555}

export VS_INDEX_NAME=${VS_INDEX_NAME:-video_frame_embeddings}
export INDEX_NAME=${INDEX_NAME:-$VS_INDEX_NAME}
export SEARCH_ENGINE=${SEARCH_ENGINE:-FaissFlat}
export DISTANCE_STRATEGY=${DISTANCE_STRATEGY:-IP}

export EMBEDDING_SERVER_PORT=${EMBEDDING_SERVER_PORT:-9777}
export MULTIMODAL_EMBEDDING_HOST=${MULTIMODAL_EMBEDDING_HOST:-multimodal-embedding-serving}
export MULTIMODAL_EMBEDDING_PORT=${MULTIMODAL_EMBEDDING_PORT:-8000}
export MULTIMODAL_EMBEDDING_ENDPOINT=${MULTIMODAL_EMBEDDING_ENDPOINT:-http://${MULTIMODAL_EMBEDDING_HOST}:${MULTIMODAL_EMBEDDING_PORT}/embeddings}
export EMBEDDING_MODEL_NAME=${EMBEDDING_MODEL_NAME:-}
export EMBEDDING_DEVICE=${EMBEDDING_DEVICE:-CPU}
export EMBEDDING_USE_OV=${EMBEDDING_USE_OV:-true}
export EMBEDDING_OV_MODELS_DIR=${EMBEDDING_OV_MODELS_DIR:-/app/ov_models}
export DEFAULT_START_OFFSET_SEC=${DEFAULT_START_OFFSET_SEC:-0}
export DEFAULT_CLIP_DURATION=${DEFAULT_CLIP_DURATION:--1}
export DEFAULT_NUM_FRAMES=${DEFAULT_NUM_FRAMES:-64}
export OV_PERFORMANCE_MODE=${OV_PERFORMANCE_MODE:-LATENCY}

export EMBEDDINGS_ENDPOINT=${EMBEDDINGS_ENDPOINT:-${MULTIMODAL_EMBEDDING_ENDPOINT}}

export DEFAULT_TOP_K=${DEFAULT_TOP_K:-20}
export MAX_TOP_K=${MAX_TOP_K:-1000}
export REQUEST_TIMEOUT_SECONDS=${REQUEST_TIMEOUT_SECONDS:-30}
export BATCH_MAX_CONCURRENCY=${BATCH_MAX_CONCURRENCY:-10}

export MILVUS_URI=${MILVUS_URI:-http://milvus-standalone:19530}
export MILVUS_TOKEN=${MILVUS_TOKEN:-}
export MILVUS_DB_NAME=${MILVUS_DB_NAME:-}
export MILVUS_INDEX_TYPE=${MILVUS_INDEX_TYPE:-FLAT}
export MILVUS_METRIC_TYPE=${MILVUS_METRIC_TYPE:-L2}

export PGVECTOR_CONNECTION_STRING=${PGVECTOR_CONNECTION_STRING:-postgresql+psycopg://postgres:postgres@pgvector-db:5432/postgres}
export PGVECTOR_DB_NAME=${PGVECTOR_DB_NAME:-postgres}
export PGVECTOR_DB_USER=${PGVECTOR_DB_USER:-postgres}
export PGVECTOR_DB_PASSWORD=${PGVECTOR_DB_PASSWORD:-postgres}
export PGVECTOR_HOST_PORT=${PGVECTOR_HOST_PORT:-5432}
export FAISS_INDEX_PATH=${FAISS_INDEX_PATH:-}
export MILVUS_HOST_PORT=${MILVUS_HOST_PORT:-19530}
export MILVUS_METRICS_HOST_PORT=${MILVUS_METRICS_HOST_PORT:-9091}

backend_compose_file="docker/compose.${RETRIEVER_BACKEND}.yaml"
requires_backend_compose=1
if [[ "$1" == "--down" || "$1" == "--clean-data" || "$1" == "--build" ]]; then
    requires_backend_compose=0
fi

if [[ "$requires_backend_compose" -eq 1 && ! -f "${backend_compose_file}" ]]; then
    echo -e "${RED}Unsupported RETRIEVER_BACKEND='${RETRIEVER_BACKEND}'.${NC}"
    echo "Expected one of: vdms, milvus, pgvector, faiss"
    if is_sourced; then
        return 1
    fi
    exit 1
fi

skip_env_validation=0
if [[ "$1" == "--down" || "$1" == "--clean-data" || "$1" == "--build" ]]; then
    skip_env_validation=1
fi

if [[ "$skip_env_validation" -eq 0 ]]; then
    if ! validate_required_env_vars; then
        if is_sourced; then
            return 1
        fi
        exit 1
    fi
fi

compose_cmd=(docker compose -f docker/compose.yaml -f "${backend_compose_file}")

add_no_proxy_host() {
    local host="$1"
    if [[ -z "$host" ]]; then
        return
    fi
    if [[ ",${no_proxy}," != *",${host},"* ]]; then
        if [[ -n "$no_proxy" ]]; then
            export no_proxy="${no_proxy},${host}"
        else
            export no_proxy="${host}"
        fi
    fi
}

add_no_proxy_host "${MULTIMODAL_EMBEDDING_HOST}"
case "${RETRIEVER_BACKEND}" in
    vdms)
        add_no_proxy_host "${VDMS_VDB_HOST}"
        ;;
    milvus)
        add_no_proxy_host "milvus-standalone"
        ;;
    pgvector)
        add_no_proxy_host "pgvector-db"
        ;;
esac

cat > .env <<EOF
TAG=${TAG}
REGISTRY=${REGISTRY}
VECTOR_RETRIEVER_HOST_PORT=${VECTOR_RETRIEVER_HOST_PORT}
VECTOR_RETRIEVER_LOG_LEVEL=${VECTOR_RETRIEVER_LOG_LEVEL}
RETRIEVER_BACKEND=${RETRIEVER_BACKEND}
VDMS_IMAGE=${VDMS_IMAGE}
MILVUS_IMAGE=${MILVUS_IMAGE}
PGVECTOR_IMAGE=${PGVECTOR_IMAGE}
VDMS_VDB_HOST=${VDMS_VDB_HOST}
VDMS_VDB_PORT=${VDMS_VDB_PORT}
VDMS_VDB_HOST_PORT=${VDMS_VDB_HOST_PORT}
VS_INDEX_NAME=${VS_INDEX_NAME}
INDEX_NAME=${INDEX_NAME}
SEARCH_ENGINE=${SEARCH_ENGINE}
DISTANCE_STRATEGY=${DISTANCE_STRATEGY}
EMBEDDING_SERVER_PORT=${EMBEDDING_SERVER_PORT}
MULTIMODAL_EMBEDDING_HOST=${MULTIMODAL_EMBEDDING_HOST}
MULTIMODAL_EMBEDDING_PORT=${MULTIMODAL_EMBEDDING_PORT}
MULTIMODAL_EMBEDDING_ENDPOINT=${MULTIMODAL_EMBEDDING_ENDPOINT}
EMBEDDING_MODEL_NAME=${EMBEDDING_MODEL_NAME}
EMBEDDING_DEVICE=${EMBEDDING_DEVICE}
EMBEDDING_USE_OV=${EMBEDDING_USE_OV}
EMBEDDING_OV_MODELS_DIR=${EMBEDDING_OV_MODELS_DIR}
DEFAULT_START_OFFSET_SEC=${DEFAULT_START_OFFSET_SEC}
DEFAULT_CLIP_DURATION=${DEFAULT_CLIP_DURATION}
DEFAULT_NUM_FRAMES=${DEFAULT_NUM_FRAMES}
OV_PERFORMANCE_MODE=${OV_PERFORMANCE_MODE}
EMBEDDINGS_ENDPOINT=${EMBEDDINGS_ENDPOINT}
DEFAULT_TOP_K=${DEFAULT_TOP_K}
MAX_TOP_K=${MAX_TOP_K}
REQUEST_TIMEOUT_SECONDS=${REQUEST_TIMEOUT_SECONDS}
BATCH_MAX_CONCURRENCY=${BATCH_MAX_CONCURRENCY}
MILVUS_URI=${MILVUS_URI}
MILVUS_TOKEN=${MILVUS_TOKEN}
MILVUS_DB_NAME=${MILVUS_DB_NAME}
MILVUS_INDEX_TYPE=${MILVUS_INDEX_TYPE}
MILVUS_METRIC_TYPE=${MILVUS_METRIC_TYPE}
MILVUS_HOST_PORT=${MILVUS_HOST_PORT}
MILVUS_METRICS_HOST_PORT=${MILVUS_METRICS_HOST_PORT}
PGVECTOR_CONNECTION_STRING=${PGVECTOR_CONNECTION_STRING}
PGVECTOR_DB_NAME=${PGVECTOR_DB_NAME}
PGVECTOR_DB_USER=${PGVECTOR_DB_USER}
PGVECTOR_DB_PASSWORD=${PGVECTOR_DB_PASSWORD}
PGVECTOR_HOST_PORT=${PGVECTOR_HOST_PORT}
FAISS_INDEX_PATH=${FAISS_INDEX_PATH}
EOF

if [ "$1" = "--nosetup" ] && [ "$#" -eq 1 ]; then
    echo "Environment prepared and .env generated"
    finish 0
elif [ "$1" = "--conf" ] && [ "$#" -eq 1 ]; then
    if ! "${compose_cmd[@]}" config; then
        echo -e "${RED}Failed to render compose configuration.${NC}" >&2
        if is_sourced; then
            return 1
        fi
        exit 1
    fi
    finish 0
elif [ "$1" = "--down" ] && [ "$#" -eq 1 ]; then
    down_all_backend_stacks
    echo "All backend stacks down"
    finish 0
elif [ "$1" = "--clean-data" ] && [ "$#" -eq 1 ]; then
    down_all_backend_stacks --remove-orphans
    remove_stack_named_volumes
    echo "All backend stacks cleaned (containers, networks, stack volumes, and orphans removed)"
    finish 0
elif [ "$1" = "--build" ]; then
    shift
    if ! run_build_script "$@"; then
        echo -e "${RED}Build failed.${NC}" >&2
        if is_sourced; then
            return 1
        fi
        exit 1
    fi
    echo "Build complete"
    finish 0
elif [[ "$1" =~ ^--up-with-(vdms|milvus|pgvector|faiss)$ ]] && [ "$#" -eq 1 ]; then
    backend="${1#--up-with-}"
    if ! docker compose -f docker/compose.yaml -f "docker/compose.${backend}.yaml" up -d --build; then
        echo -e "${RED}Failed to start vector-retriever with ${backend} overlay.${NC}" >&2
        if is_sourced; then
            return 1
        fi
        exit 1
    fi
    docker ps | grep vector-retriever || true
    echo "vector-retriever is up (with ${backend} overlay)"
    finish 0
elif [ "$#" -eq 0 ]; then
    if ! "${compose_cmd[@]}" up -d --build; then
        echo -e "${RED}Failed to start vector-retriever (backend=${RETRIEVER_BACKEND}).${NC}" >&2
        if is_sourced; then
            return 1
        fi
        exit 1
    fi
    docker ps | grep vector-retriever || true
    echo "vector-retriever is up (backend=${RETRIEVER_BACKEND})"
    finish 0
else
    echo -e "${RED}Invalid arguments.${NC}"
    print_usage
    finish 1
fi
