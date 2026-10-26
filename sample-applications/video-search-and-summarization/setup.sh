#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Color codes for terminal output
RED='\033[0;31m'
MAGENTA='\033[0;35m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

# =================== Setup Config Directories ======================
nginx_config_dir="${PWD}/config/nginx"
# Host root for all model assets
export OV_MODELS_ROOT="${PWD}/ov_models"
export MODEL_DOWNLOAD_CTR_NAME=${MODEL_DOWNLOAD_CTR_NAME:-vss-model-download}

# ================================= PULL POLICY ======================================
# --pull-always (alias --force-pull) or PULL_ALWAYS=true makes a deployment check the
# registry for every image, so moving tags such as `latest` are refreshed instead of
# reusing a cached copy. The flag may appear anywhere and is removed before mode parsing.
# vss_pull_always is reset on every run, so the flag does not persist in the sourcing shell.
vss_pull_always=false
case "${PULL_ALWAYS:-false}" in
    true|TRUE|True|1) vss_pull_always=true ;;
    false|FALSE|False|0) ;;
    *)
        echo -e "${RED}ERROR: PULL_ALWAYS must be true or false (got '${PULL_ALWAYS}').${NC}" >&2
        return 1
        ;;
esac
vss_args=()
for vss_arg in "$@"; do
    case "$vss_arg" in
        --pull-always|--force-pull) vss_pull_always=true ;;
        *) vss_args+=("$vss_arg") ;;
    esac
done
set -- "${vss_args[@]}"
unset vss_arg vss_args

# ================================= SETUP ALIASES ======================================
if [ "$#" -eq 1 ] && [ "$1" = "config" ]; then    # config with no args defaults to both summary and search
    set -- "--dual" "config"
elif [ "$#" -eq 1 ] && [ "$1" = "--down" ]; then  # --down is an alias for --stop
    set -- "--stop"
elif [ "$#" -eq 2 ] && [ "$1" = "config" ]; then  # `config [mode]` gets aliased to `[mode] config` (older impl.)
    set -- "$2" "config"
elif [ "$#" -eq 3 ] && [ "$1" = "config" ]; then  # `[config arg1 arg2]` gets aliased to `[arg1 arg2 config]` (older impl.)
    set -- "$2" "$3" "config"
elif [ "$#" -eq 1 ] && [ "$1" = "-h" ]; then 
    set -- "--help"
fi

# Alias `--search --summary` and `--summary --search` to `--dual`, with optional `config` arg.
if [ "$#" -ge 2 ] && ([ "$1" = "--search" ] && [ "$2" = "--summary" ]) \
    || ([ "$1" = "--summary" ] && [ "$2" = "--search" ]); then
    if [ "$3" = "config" ]; then
        set -- "--dual" "config"
    elif [ "$#" -eq 2 ]; then
        set -- "--dual"
    fi
# Alias `--summary-and-search` to `--unified`, with optional `config` arg.
elif [ "$#" -ge 1 ] && { [ "$1" = "--summary-and-search" ] || [ "$1" = "--all" ] || [ "$1" = "--search-and-summary" ]; }; then
    if [ "$#" -eq 2 ] && [ "$2" = "config" ]; then
        set -- "--unified" "config"
    elif [ "$#" -eq 1 ]; then
        set -- "--unified"
    fi
fi

if [ "$vss_pull_always" = true ] && { [ "$2" = "config" ] || [ "$1" = "--stop" ] \
    || [ "$1" = "--clean-data" ] || [ "$1" = "--setenv" ]; }; then
    echo -e "${YELLOW}Note: --pull-always / PULL_ALWAYS only applies when deploying; ignored for this command.${NC}"
fi

# =================== Function Definitions =========================
stop_containers() {
    echo -e "${YELLOW}Bringing down all the Docker containers... ${NC}"
    docker rm -f "${MODEL_DOWNLOAD_CTR_NAME}" >/dev/null 2>&1
    # MCP Inspector is no longer shipped; remove one left by an older release.
    docker rm -f vss-mcp-inspector >/dev/null 2>&1
    docker compose \
        -f docker/compose.base.yaml \
        -f docker/compose.summary.yaml \
        -f docker/compose.vllm.yaml \
        -f docker/compose.vllm.xpu.yaml \
        -f docker/compose.search.yaml \
        -f docker/compose.search.vdms.yaml \
        -f docker/compose.search.milvus.yaml \
        -f docker/compose.ui.yaml \
        -f docker/compose.metrics-manager.yaml \
        -f docker/compose.mcp.yaml \
        --profile ovms --profile vlm-ov --profile vllm --profile vllm-xpu \
        --profile dual_ui --profile singleton_unified_ui \
        --profile singleton_summary_ui \
        --profile singleton_search_ui \
        --profile mcp \
        down
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to stop and remove containers.${NC}" >&2
        return 1
    fi
    echo -e "${GREEN}All containers were successfully stopped and removed. ${NC}"
    return 0
}

remove_volumes() {
    echo -e "${YELLOW}Removing Docker volumes... ${NC}"
    # User-data volumes only. Model-cache volumes (docker_dataprep-yolox-models,
    # docker_ov-models, docker_vllm_model_cache) are intentionally preserved so
    # a --clean-data does not force a costly re-download of models.
    # Milvus volumes are included because they hold vector data when the Milvus
    # backend is used; they simply don't exist (and are skipped) otherwise.
    local user_data_volumes="\
docker_minio_data \
docker_pg_data \
docker_vdms-db \
docker_milvus-db \
docker_milvus-etcd \
docker_data-prep"

    local removed=""
    local failed=""
    for vol in $user_data_volumes; do
        # Skip volumes that don't exist for the current mode: passing a missing
        # volume name to `docker volume rm` makes it exit non-zero even when the
        # volumes that do exist were removed successfully, which previously
        # produced a misleading "Could not remove all volumes" note.
        if ! docker volume inspect "$vol" >/dev/null 2>&1; then
            continue
        fi
        if docker volume rm "$vol" >/dev/null 2>&1; then
            removed="$removed $vol"
        else
            failed="$failed $vol"
        fi
    done

    if [ -n "$failed" ]; then
        echo -e "${YELLOW}Note: These volumes exist but could not be removed (likely still in use by a running container):${failed}${NC}"
        echo -e "${YELLOW}Stop the containers first (make stop) and retry. ${NC}" >&2
        return 1
    fi
    if [ -z "$removed" ]; then
        echo -e "${GREEN}No user-data volumes present to remove. ${NC}"
        return 0
    fi
    echo -e "${GREEN}All user-data volumes were successfully removed:${removed} ${NC}"
    return 0
}

show_concise_help() {
    echo -e "Video Search and Summarization Application setup script v1.0"
    echo -e "Copyright (C) 2026 Intel Corporation"
    echo -e "${YELLOW}USAGE: ${GREEN}source setup.sh ${BLUE}--summary [--search] | --search [--summary] | --search-and-summary | --stop | --clean-data | config${NC} [--pull-always]"
    echo -e "${YELLOW}EXAMPLES:"
    echo -e "${GRAY}source setup.sh --summary"
    echo -e "source setup.sh --search"
    echo -e "source setup.sh --summary --search"
    echo -e "source setup.sh --summary --pull-always${NC}"
    echo -e  "${MAGENTA}Use ${YELLOW}--help${NC}${MAGENTA} for detailed usage information and options.${NC}"
}

enforce_npu_int4_weight_format() {
    local model_type="$1"
    local target_device="$2"
    local weight_format_variable="$3"
    local weight_format="${!weight_format_variable}"

    if [[ "${target_device^^}" == "NPU" && "$weight_format" != "int4" ]]; then
        echo -e "[ovms-service] ${YELLOW}NPU supports only int4; overriding ${model_type} weight format ${weight_format} → int4.${NC}"
        export "${weight_format_variable}=int4"
    fi
}

# OpenVINO/* repos are pre-converted at the precision encoded in the repo name
# (e.g. OpenVINO/Qwen3.5-4B-int8-ov). Use that precision instead of the device
# default or user override so model-download pulls the repo as-is rather than
# falling back to a conversion, which cannot re-quantize pre-converted models.
use_openvino_model_weight_format() {
    local model_type="$1"
    local model="$2"
    local weight_format_variable="$3"
    local weight_format="${!weight_format_variable}"
    local short_name="${model##*/}"

    is_openvino_namespace_model "$model" || return 0
    [[ "${short_name,,}" =~ -(int4|int8|fp16|fp32|nf4)(-|$) ]] || return 0
    local repo_weight_format="${BASH_REMATCH[1]}"

    # model-download only accepts int4/int8/fp16/fp32 and pulls by that token in the repo name.
    if [[ "$repo_weight_format" == "nf4" ]]; then
        echo -e "[ovms-service] ${RED}ERROR: ${model_type} ${model} is pre-converted as nf4, which model-download cannot fetch. Use an int4/int8/fp16 variant of this model.${NC}" >&2
        return 1
    fi

    if [[ "$weight_format" != "$repo_weight_format" ]]; then
        echo -e "[ovms-service] ${YELLOW}${model_type} ${model} is pre-converted as ${repo_weight_format}; using ${repo_weight_format} instead of ${weight_format:-default}.${NC}"
        export "${weight_format_variable}=${repo_weight_format}"
    fi
}

show_full_help() {
    echo -e  "-----------------------------------------------------------------"
    echo -e  "${YELLOW}USAGE: ${GREEN}source setup.sh ${BLUE}[ --summary [--search] [config] | --search [--summary] [config] | --search-and-summary [config] |"
    echo -e  "                         --stop | --clean-data | --set-env | --help ] [--pull-always]"
    echo -e  "${YELLOW}"
    echo -e  "                -h, --help:  Shows this help message."
    echo -e  "                 --summary:  Deploy Video Summary Application."
    echo -e  "                             ${GRAY}Use with ${GREEN}--search${GRAY} option to deploy both summary and search applications together.${NC}"
    echo -e "${YELLOW}                  --search:  Deploy Video Search Application."
    echo -e  "                             ${GRAY}Use with ${GREEN}--summary${GRAY} option to deploy both search and summary applications together.${NC}"
    echo -e  "${YELLOW}      --summary-and-search:  Deploy a modified Video Search application which does video summarization first and searches on summary content."
    echo -e  "                             ${GRAY}Every deployment also starts the VSS MCP tool server at http://<HOST_IP>:${APP_HOST_PORT}/mcp (via the nginx gateway); ${GREEN}--stop${GRAY} brings it down with the stack.${NC}"
    echo -e  "${YELLOW}                  --setenv:  Set environment variables without setting up application or starting any containers."
    echo -e  "            --down, --stop:  Bring down all the docker containers for the application."
    echo -e  "              --clean-data:  Bring down all the docker containers and remove all docker volumes for the user data."
    echo -e  "                             ${GRAY}Asks for confirmation; set ${GREEN}CONFIRM=yes${GRAY} to skip the prompt.${NC}"
    echo -e  "             --pull-always:  With a deploy mode (alias ${GREEN}--force-pull${NC}), check the registry for every image and pull newer ones"
    echo -e  "                             (Compose ${GREEN}up --pull always${NC} and the model-download container), so tags such as ${GREEN}latest${NC} are refreshed."
    echo -e  "                             ${GRAY}Same as ${GREEN}PULL_ALWAYS=true${GRAY}. Images that exist only locally are kept when the pull fails;"
    echo -e  "                             a registry image with the same name and tag replaces a locally built one.${NC}"
    echo -e  "             [Mode] config:  Print the final compose configuration with all environment variables resolved without"
    echo -e  "                             starting containers."
    echo -e  "                             ${GRAY}Mode defaults to ${GREEN}--summary --search${GRAY} when omitted."
    echo -e  "                             Supported Modes: ${GREEN}--summary [--search], --search [--summary], --summary-and-search${NC}"
    echo -e  "-----------------------------------------------------------------"
}

# =================== Argument Parsing and Handling =========================
if [ "$#" -eq 0 ]; then
    show_concise_help && return 0
elif [ "$#" -eq 1 ] && [ "$1" = "--help" ]; then
    show_full_help && set -- && return 0
elif [ "$#" -gt 2 ]; then
    echo -e "${RED}ERROR: Too many arguments provided.${NC}" >&2
    echo -e "${YELLOW}Use --help for usage information${NC}" >&2
    set --
    return 1
fi

if [ "$#" -ge 1 ] \
     && [ "$1" != "--dual" ] && [ "$1" != "--unified" ] \
     && [ "$1" != "--summary" ] && [ "$1" != "--search" ] \
     && [ "$1" != "--stop" ] && [ "$1" != "--clean-data" ] \
     && [ "$1" != "--setenv" ] && [ "$1" != "config" ] \
     && [ "$1" != "--help" ]; then
    # Default case for unrecognized first option
    echo -e "${RED}Unknown option: $1 ${NC}" >&2
    echo -e "${YELLOW}Use --help for usage information${NC}" >&2
    set --
    return 1

elif [ "$#" -eq 2 ] && [ "$1" = "config" ] \
    && [ "$2" != "--summary" ] && [ "$2" != "--search" ] \
    && [ "$2" != "--dual" ] && [ "$2" != "--unified" ]; then
    echo -e "${RED}Invalid argument combination: '$1 $2'${NC}" >&2
    echo -e "${YELLOW}Valid forms: config, config --summary, config --search, config --search-and-summary${NC}" >&2
    echo -e "${YELLOW}Use --help for usage information${NC}" >&2
    set --
    return 1

elif [ "$#" -eq 2 ] && [ "$1" != "config" ] && [ "$2" != "config" ]; then
    echo -e "${RED}Invalid argument combination: '$1 $2'${NC}" >&2
    echo -e "${YELLOW}Valid two-argument forms are '<mode> config' or 'config <mode>'${NC}" >&2
    echo -e "${YELLOW}Use --help for usage information${NC}" >&2
    set --
    return 1

elif [ "$1" = "--stop" ] || [ "$1" = "--clean-data" ]; then
        # Bring down all the Docker containers
    stop_containers || return 1
    # Remove volumes if --clean-data is specified
    if [ "$1" = "--clean-data" ]; then
        remove_volumes || return 1
        echo -e "${GREEN}Clean operation completed successfully! ${NC}"
    fi
    return 0
fi


# ================================== Export Environment Variables ===================================
# Base configuration
export APP_HOST_PORT=${APP_HOST_PORT:-12345}  # Default host port for nginx proxy (external access to UIs)
export HOST_IP=${HOST_IP:-$(ip route get 1 | awk '{print $7}')}
# Default VSS_IP to HOST_IP: the MCP server (always part of the stack) calls the
# VSS gateway at this address and puts it in every URL it returns to agents.
export VSS_IP=${VSS_IP:-${HOST_IP}}
# Externally reachable gateway URL Pipeline Manager uses in links it returns
export PM_PUBLIC_BASE_URL=${PM_PUBLIC_BASE_URL:-http://${HOST_IP}:${APP_HOST_PORT}}
export TAG=${TAG:-latest}

# If REGISTRY_URL is set, ensure it ends with a trailing slash
# Using parameter expansion to conditionally append '/' if not already present
[[ -n "$REGISTRY_URL" ]] && REGISTRY_URL="${REGISTRY_URL%/}/"

# If PROJECT_NAME is set, ensure it ends with a trailing slash
[[ -n "$PROJECT_NAME" ]] && PROJECT_NAME="${PROJECT_NAME%/}/"

export REGISTRY="${REGISTRY_URL}${PROJECT_NAME}"
echo -e "${GREEN}Using registry: ${YELLOW}$REGISTRY ${NC}"

export VLM_MODEL_NAME=${VLM_MODEL_NAME}
# Keep user override from environment if provided; device-based default is set later.
export VLM_COMPRESSION_WEIGHT_FORMAT=${VLM_COMPRESSION_WEIGHT_FORMAT:-}
export VLM_TARGET_DEVICE=${VLM_TARGET_DEVICE:-CPU}
export ENABLE_VLLM=${ENABLE_VLLM:-false}
export ENABLE_VLLM_GPU=${ENABLE_VLLM_GPU:-false}
export USER_GROUP_ID=$(id -g)
export VIDEO_GROUP_ID=$(getent group video | awk -F: '{printf "%s\n", $3}')
export RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')

# env for pipeline-manager
PM_SUMMARIZATION_MAX_COMPLETION_TOKENS_DEFAULTED=false
if [[ -z "${PM_SUMMARIZATION_MAX_COMPLETION_TOKENS+x}" ]]; then
    export PM_SUMMARIZATION_MAX_COMPLETION_TOKENS=4000
    PM_SUMMARIZATION_MAX_COMPLETION_TOKENS_DEFAULTED=true
fi
PM_CAPTIONING_MAX_COMPLETION_TOKENS_DEFAULTED=false
if [[ -z "${PM_CAPTIONING_MAX_COMPLETION_TOKENS+x}" ]]; then
    export PM_CAPTIONING_MAX_COMPLETION_TOKENS=1024
    PM_CAPTIONING_MAX_COMPLETION_TOKENS_DEFAULTED=true
fi
PM_LLM_MAX_CONTEXT_LENGTH_DEFAULTED=false
if [[ -z "${PM_LLM_MAX_CONTEXT_LENGTH+x}" ]]; then
    export PM_LLM_MAX_CONTEXT_LENGTH=90000
    PM_LLM_MAX_CONTEXT_LENGTH_DEFAULTED=true
fi
PM_LLM_CONCURRENT_DEFAULTED=false
if [[ -z "${PM_LLM_CONCURRENT+x}" ]]; then
    export PM_LLM_CONCURRENT=2
    PM_LLM_CONCURRENT_DEFAULTED=true
fi
PM_VLM_CONCURRENT_DEFAULTED=false
if [[ -z "${PM_VLM_CONCURRENT+x}" ]]; then
    export PM_VLM_CONCURRENT=6
    PM_VLM_CONCURRENT_DEFAULTED=true
fi
PM_MULTI_FRAME_COUNT_DEFAULTED=false
if [[ -z "${PM_MULTI_FRAME_COUNT+x}" ]]; then
    export PM_MULTI_FRAME_COUNT=12
    PM_MULTI_FRAME_COUNT_DEFAULTED=true
fi

# env for ovms-service
# Track whether LLM_TARGET_DEVICE was explicitly provided.
LLM_TARGET_DEVICE_DEFAULTED=false
if [[ -z "${LLM_TARGET_DEVICE+x}" ]]; then
    export LLM_TARGET_DEVICE=CPU
    LLM_TARGET_DEVICE_DEFAULTED=true
else
    export LLM_TARGET_DEVICE=${LLM_TARGET_DEVICE}
fi
# LLM_MODEL_NAME is derived for the active deployment. OVMS_LLM_MODEL_NAME is
# the explicit opt-in for a separate final-summary model.
export LLM_COMPRESSION_WEIGHT_FORMAT=${LLM_COMPRESSION_WEIGHT_FORMAT:-}
# Static prompt/response token limits compiled into NPU stateful LLM servables
# (OVMS defaults are 1024/128). See apply_ovms_npu_llm_limits.
export OVMS_NPU_MAX_PROMPT_LEN=${OVMS_NPU_MAX_PROMPT_LEN:-8192}
export OVMS_NPU_MIN_RESPONSE_LEN=${OVMS_NPU_MIN_RESPONSE_LEN:-1024}

# env for rabbitmq
export RABBITMQ_USER=${RABBITMQ_USER}  # Set this in your shell before running the script
export RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD} # Set this in your shell before running the script

# env for postgres
export POSTGRES_USER=${POSTGRES_USER}  # Set this in your shell before running the script
export POSTGRES_PASSWORD=${POSTGRES_PASSWORD}  # Set this in your shell before running the script

# env for minio-service
export MINIO_ROOT_USER=${MINIO_ROOT_USER} # Set this in your shell before running the script
export MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD} # Set this in your shell before running the script
export OVMS_ALLOWED_MEDIA_DOMAINS=${OVMS_ALLOWED_MEDIA_DOMAINS:-${MINIO_HOST:-minio-service},localhost}

# env for vdms-vector-db
export VDMS_VDB_HOST_PORT=55555
export VDMS_VDB_HOST=vdms-vector-db

# env for multimodal-embedding-serving
# Consumed by video-search and vector-retriever; both reach the service over the
# compose network, so the defaults must be exported and not left to interpolation.
export MULTIMODAL_EMBEDDING_HOST=${MULTIMODAL_EMBEDDING_HOST:-multimodal-embedding-serving}
export MULTIMODAL_EMBEDDING_ENDPOINT=${MULTIMODAL_EMBEDDING_ENDPOINT:-http://${MULTIMODAL_EMBEDDING_HOST}:8000/embeddings}

# ---------------------------------------------------------------------------
# Vector database backend selection (search path)
#   VECTORDB_BACKEND=vdms   (default) — multimodal-dataprep writes to VDMS and
#                                       the vector-retriever-vdms image reads it.
#   VECTORDB_BACKEND=milvus           — multimodal-dataprep writes to Milvus and
#                                       the vector-retriever-milvus image reads it.
# For BOTH backends, video-search delegates ALL similarity search to the
# always-on vector-retriever microservice; it holds no vector DB client itself.
# Object storage stays on MinIO for both backends.
# ---------------------------------------------------------------------------
export VECTORDB_BACKEND=${VECTORDB_BACKEND:-vdms}
if [ "$VECTORDB_BACKEND" != "vdms" ] && [ "$VECTORDB_BACKEND" != "milvus" ]; then
    echo -e "${RED}ERROR: VECTORDB_BACKEND must be 'vdms' or 'milvus' (got '${VECTORDB_BACKEND}').${NC}" >&2
    return 1
fi
# The vector-retriever image flavor is baked at build time from this value
# (vector-retriever-${RETRIEVER_BACKEND}); it drives image + backend env in
# docker/compose.search.yaml.
export RETRIEVER_BACKEND=${VECTORDB_BACKEND}
export VECTOR_RETRIEVER_HOST_PORT=${VECTOR_RETRIEVER_HOST_PORT:-6008}
# Shared vector similarity metric/index; MUST match on dataprep + retriever.
export VDB_METRIC_TYPE=${VDB_METRIC_TYPE:-IP}
export VDB_INDEX_TYPE=${VDB_INDEX_TYPE:-FLAT}
# video-search always delegates its similarity search to vector-retriever /query.
export VS_RETRIEVER_ENDPOINT=${VS_RETRIEVER_ENDPOINT:-http://vector-retriever:8000/query}
if [ "$VECTORDB_BACKEND" = "milvus" ]; then
    export MILVUS_HOST_PORT=${MILVUS_HOST_PORT:-19530}
    export MILVUS_METRICS_HOST_PORT=${MILVUS_METRICS_HOST_PORT:-9091}
    export MILVUS_URI=${MILVUS_URI:-http://milvus-standalone:19530}
fi

# env for multimodal-dataprep-ms
export MM_DATAPREP_HOST_PORT=6016
export MM_DATAPREP_HOST=multimodal-dataprep
export MM_DATAPREP_ENDPOINT=http://$MM_DATAPREP_HOST:8000
export VIDEO_UPLOAD_ENDPOINT=http://pipeline-manager:3000
export DEFAULT_BUCKET_NAME="video-summary"

# YOLOX model volume configuration for object detection
export YOLOX_MODELS_VOLUME_NAME="dataprep-yolox-models"
export YOLOX_MODELS_MOUNT_PATH="/app/models/yolox"

# Frame processing settings
export FRAME_INTERVAL=${FRAME_INTERVAL:-15}
export ENABLE_OBJECT_DETECTION=${ENABLE_OBJECT_DETECTION:-true}
export DETECTION_CONFIDENCE=${DETECTION_CONFIDENCE:-0.85}
# ROI consolidation parameters for grouping overlapping detections
# ROI_CONSOLIDATION_IOU_THRESHOLD: IoU threshold used to cluster ROIs (higher = stricter merging)
# ROI_CONSOLIDATION_CLASS_AWARE: only merge ROIs with matching class labels when true
# ROI_CONSOLIDATION_CONTEXT_SCALE: expands merged ROI by a fraction of its size
export ROI_CONSOLIDATION_ENABLED=${ROI_CONSOLIDATION_ENABLED:-false}
export ROI_CONSOLIDATION_IOU_THRESHOLD=${ROI_CONSOLIDATION_IOU_THRESHOLD:-0.2}
export ROI_CONSOLIDATION_CLASS_AWARE=${ROI_CONSOLIDATION_CLASS_AWARE:-false}
export ROI_CONSOLIDATION_CONTEXT_SCALE=${ROI_CONSOLIDATION_CONTEXT_SCALE:-0.2}
export FRAMES_TEMP_DIR=${FRAMES_TEMP_DIR:-"/tmp/dataprep"}

# Application configuration
export MM_DATAPREP_LOG_LEVEL=${MM_DATAPREP_LOG_LEVEL:-INFO}
export MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS=${MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS:-true}
export MAX_PARALLEL_WORKERS=${MAX_PARALLEL_WORKERS:-""}
export EMBEDDING_BATCH_SIZE=${EMBEDDING_BATCH_SIZE:-32}
export ALLOW_ORIGINS=${ALLOW_ORIGINS:-*}
export ALLOW_METHODS=${ALLOW_METHODS:-*}
export ALLOW_HEADERS=${ALLOW_HEADERS:-*}

# env for multimodal-embedding-serving (unified embedding service)
export EMBEDDING_SERVER_PORT=9777
export DEFAULT_START_OFFSET_SEC=0
export DEFAULT_CLIP_DURATION=${DEFAULT_CLIP_DURATION:--1}
export DEFAULT_NUM_FRAMES=64
export EMBEDDING_USE_OV=${EMBEDDING_USE_OV:-$SDK_USE_OPENVINO}
# Per-component device selection (CPU default | GPU | NPU). Each component is
# independent — parity with the Helm charts. No "baseline" device.
#   DATAPREP_EMBEDDING_DEVICE → embedding in multimodal-dataprep (in-process SDK)
#   DATAPREP_DETECTION_DEVICE → YOLOX object detection in multimodal-dataprep
#   MME_EMBEDDING_DEVICE      → embedding in multimodal-embedding-serving (used by video-search)
export DATAPREP_EMBEDDING_DEVICE=${DATAPREP_EMBEDDING_DEVICE:-"CPU"}
export DATAPREP_DETECTION_DEVICE=${DATAPREP_DETECTION_DEVICE:-"CPU"}
export MME_EMBEDDING_DEVICE=${MME_EMBEDDING_DEVICE:-"CPU"}

# Device Configuration
export SDK_USE_OPENVINO=${SDK_USE_OPENVINO:-true}

# Easy-button: put the in-process DataPrep embedding on GPU.
if [ "$ENABLE_EMBEDDING_GPU" = true ]; then
    export DATAPREP_EMBEDDING_DEVICE=GPU
fi


# Device Configuration Helper Functions
# Validates host accelerator availability and enforces OpenVINO when any component
# targets GPU/NPU. Operates on the per-component device values (no baseline device).
configure_device() {
    local accel="$1"  # "GPU", "NPU", or "CPU"

    if [[ "${accel}" == GPU* ]]; then
        echo -e "${YELLOW}GPU acceleration requested for one or more components...${NC}"
        if ! lspci | grep -i "vga.*intel" > /dev/null 2>&1; then
            echo -e "${RED}Warning: No Intel GPU detected. GPU mode may not work properly.${NC}" >&2
        else
            echo -e "${GREEN}Intel GPU detected${NC}"
        fi
        if [[ ! -d "/dev/dri" ]]; then
            echo -e "${RED}Warning: /dev/dri not found. GPU acceleration may not be available.${NC}" >&2
        else
            echo -e "${GREEN}DRI devices found for GPU acceleration${NC}"
        fi
        export SDK_USE_OPENVINO=true  # Force OpenVINO for GPU mode
    elif [[ "${accel}" == NPU* ]]; then
        echo -e "${YELLOW}NPU acceleration requested for one or more components...${NC}"
        if [[ ! -e "/dev/accel/accel0" ]]; then
            echo -e "${RED}Warning: /dev/accel/accel0 not found. NPU acceleration may not be available.${NC}" >&2
        else
            echo -e "${GREEN}NPU device found for acceleration${NC}"
        fi
        export SDK_USE_OPENVINO=true  # Force OpenVINO for NPU mode
    else
        echo -e "${BLUE}CPU mode configured for all components${NC}"
    fi
}

# Detect accelerator usage across the per-component devices and validate the host.
if [[ "${DATAPREP_EMBEDDING_DEVICE}" == GPU* ]] || [[ "${DATAPREP_DETECTION_DEVICE}" == GPU* ]] || [[ "${MME_EMBEDDING_DEVICE}" == GPU* ]]; then
    configure_device "GPU"
elif [[ "${DATAPREP_EMBEDDING_DEVICE}" == NPU* ]] || [[ "${DATAPREP_DETECTION_DEVICE}" == NPU* ]] || [[ "${MME_EMBEDDING_DEVICE}" == NPU* ]]; then
    configure_device "NPU"
else
    configure_device "CPU"
fi

# Keep embedding service OpenVINO mode aligned with final SDK_USE_OPENVINO/device resolution
export EMBEDDING_USE_OV=${EMBEDDING_USE_OV:-$SDK_USE_OPENVINO}
if [[ "${MME_EMBEDDING_DEVICE}" == GPU* ]] || [[ "${MME_EMBEDDING_DEVICE}" == NPU* ]]; then
    export EMBEDDING_USE_OV=true
fi

# GPU decodes larger frame batches faster; CPU keeps the compose default (64).
# INFER_BATCH_SIZE is omitted because its compose default (32) is already optimal.
if [[ "${MME_EMBEDDING_DEVICE}" == GPU* ]]; then
    export VIDEO_FRAME_BATCH_SIZE=${VIDEO_FRAME_BATCH_SIZE:-256}
fi

if [ $1 != "--summary" ]; then
    if [ "$1" = "--unified" ]; then
        embedding_model_display="${TEXT_EMBEDDING_MODEL:-"(not provided)"}"
    else
        embedding_model_display="${MULTIMODAL_EMBEDDING_MODEL:-"(not provided)"}"
    fi

    embedding_endpoint_display=${MULTIMODAL_EMBEDDING_ENDPOINT:-"(not configured)"}

    echo -e "[multimodal-dataprep] ${BLUE}Runtime Summary (per-component devices, default CPU):${NC}"
    echo -e "  • [multimodal-dataprep] Embedding Device: ${YELLOW}${DATAPREP_EMBEDDING_DEVICE}${NC} (in-process SDK embedding)."
    echo -e "  • [multimodal-dataprep] Detection Device: ${YELLOW}${DATAPREP_DETECTION_DEVICE}${NC}"
    echo -e "  • [multimodal-embedding-serving] Embedding Device: ${YELLOW}${MME_EMBEDDING_DEVICE}${NC} (used by video-search at ${embedding_endpoint_display})."
    echo -e "  • [multimodal-embedding-serving] Embedding Model: ${YELLOW}${embedding_model_display}${NC}"
fi

# env for video-search
export VS_WATCHER_DIR=${VS_WATCHER_DIR:-$PWD/data}
export VS_DELETE_PROCESSED_FILES=${VS_DELETE_PROCESSED_FILES:-false}
export VS_INITIAL_DUMP=${VS_INITIAL_DUMP:-false}
export VS_WATCH_DIRECTORY_RECURSIVE=${VS_WATCH_DIRECTORY_RECURSIVE:-false}
export VS_DEBOUNCE_TIME=${VS_DEBOUNCE_TIME:-10}
export VS_WATCH_BATCH_SIZE=${VS_WATCH_BATCH_SIZE:-10}
export VS_BATCH_JOB_POLL_INTERVAL_SECONDS=${VS_BATCH_JOB_POLL_INTERVAL_SECONDS:-0.5}
export VS_BATCH_JOB_TIMEOUT_SECONDS=${VS_BATCH_JOB_TIMEOUT_SECONDS:-3600}
export VS_HOST=video-search
export VS_ENDPOINT=http://$VS_HOST:8000

# If nginx not being used, set this in your shell with pipeline manager's complete url with host and port. 
export UI_PM_ENDPOINT=${UI_PM_ENDPOINT:-/manager}
# if nginx not being used, set this in your shell with minio's complete url with host and port.
export UI_ASSETS_ENDPOINT=${UI_ASSETS_ENDPOINT:-/datastore}

export CONFIG_SOCKET_APPEND=${CONFIG_SOCKET_APPEND} # Set this to CONFIG_ON in your shell, if nginx not being used

# Metrics Manager toggle for search (disabled by default)
export ENABLE_METRICS_MANAGER=${ENABLE_METRICS_MANAGER:-false}

# Object detection model (ultralytics hub id)   
export OD_MODEL_NAME=${OD_MODEL_NAME}
# Default object detection model; used as fallback for unsupported selections.
OD_MODEL_DEFAULT="yolov8l"
if [ "$1" != "--search" ]; then
    case "$OD_MODEL_NAME" in
        *-world|*-world[0-9]*|*-worldv[0-9]*)
            echo -e "[video-ingestion] ${YELLOW}Warning: object detection model '${RED}${OD_MODEL_NAME}${YELLOW}' (YOLO-World) is not supported. Falling back to the default model '${GREEN}${OD_MODEL_DEFAULT}${YELLOW}'.${NC}" >&2
            export OD_MODEL_NAME="$OD_MODEL_DEFAULT"
            ;;
    esac
    export OD_MODEL_DOWNLOAD_PATH="object-detection"
    # Host IR dir: <root>/<download_path>/ultralytics/public/<model>(/FP32/<model>.xml)
    export OD_MODEL_OUTPUT_DIR=${OV_MODELS_ROOT}/${OD_MODEL_DOWNLOAD_PATH}/ultralytics/public/${OD_MODEL_NAME}
    # These are derived for the active deployment from the selected OD model.
    # Recompute them so sourced runs cannot retain a stale model path.
    export EVAM_DETECTION_MODEL="${OD_MODEL_NAME}"
    export EVAM_DETECTION_MODEL_PATH="/home/pipeline-server/models/${OD_MODEL_DOWNLOAD_PATH}/ultralytics/public/${OD_MODEL_NAME}/FP32/${OD_MODEL_NAME}.xml"
    echo -e "[video-ingestion] ${GREEN}Object detection model: ${YELLOW}${OD_MODEL_NAME}${GREEN} (output: ${YELLOW}${OD_MODEL_OUTPUT_DIR}${GREEN})${NC}"
fi


# Fail with a consistent error when a required environment variable is unset.
# Usage: require_env VAR ["extra hint line"]
require_env() {
    [ -n "${!1}" ] && return 0
    echo -e "${RED}ERROR: $1 is not set in your shell environment.${NC}" >&2
    [ -n "$2" ] && echo -e "${YELLOW}$2${NC}" >&2
    return 1
}

# Verify if required environment variables are set in current shell, only when container down or clean is not requested.
if [ "$1" != "--down" ] && [ "$1" != "--stop" ] && [ "$1" != "--clean-data" ] && [ "$2" != "config" ]; then
    for required_var in MINIO_ROOT_USER MINIO_ROOT_PASSWORD POSTGRES_USER POSTGRES_PASSWORD RABBITMQ_USER RABBITMQ_PASSWORD; do
        require_env "$required_var" || return 1
    done
    if [ "$1" != "--search" ]; then
        for required_var in VLM_MODEL_NAME ENABLED_WHISPER_MODELS OD_MODEL_NAME; do
            require_env "$required_var" "This is required for all modes except --search." || return 1
        done
    fi
    if { [ "$1" = "--search" ] || [ "$1" = "--dual" ]; } && [ -z "$MULTIMODAL_EMBEDDING_MODEL" ]; then
        echo -e "${RED}ERROR: MULTIMODAL_EMBEDDING_MODEL is not set in your shell environment.${NC}" >&2
        echo -e "${YELLOW}This is required for Video Search embedding.${NC}" >&2
        return 1
    fi

    # Enforce dedicated text-embedding selection only for unified mode.
    if [ "$1" = "--unified" ]; then
        require_env TEXT_EMBEDDING_MODEL "This is required for --unified/--all mode." || return 1
    fi

    # Validate OVMS_CACHE_SIZE_GB if user has set it
    if [[ -n "${OVMS_CACHE_SIZE_GB:-}" ]] && ! [[ "$OVMS_CACHE_SIZE_GB" =~ ^[1-9][0-9]*$ ]]; then
        echo -e "${RED}ERROR: OVMS_CACHE_SIZE_GB must be a positive integer (got '${OVMS_CACHE_SIZE_GB}').${NC}" >&2
        echo -e "${YELLOW}This value sets the OVMS KV cache size in GB (e.g., 4, 8, 10).${NC}" >&2
        return 1
    fi

    # Validate OVMS_MAX_NUM_SEQS if user has set it
    if [[ -n "${OVMS_MAX_NUM_SEQS:-}" ]] && ! [[ "$OVMS_MAX_NUM_SEQS" =~ ^[1-9][0-9]*$ ]]; then
        echo -e "${RED}ERROR: OVMS_MAX_NUM_SEQS must be a positive integer (got '${OVMS_MAX_NUM_SEQS}').${NC}" >&2
        echo -e "${YELLOW}This value caps how many sequences OVMS batches together (e.g., 16, 32).${NC}" >&2
        return 1
    fi

    # Validate the NPU LLM token limits (always set; defaults 8192/1024)
    for npu_limit_var in OVMS_NPU_MAX_PROMPT_LEN OVMS_NPU_MIN_RESPONSE_LEN; do
        if ! [[ "${!npu_limit_var}" =~ ^[1-9][0-9]*$ ]]; then
            echo -e "${RED}ERROR: ${npu_limit_var} must be a positive integer (got '${!npu_limit_var}').${NC}" >&2
            return 1
        fi
    done
    if (( OVMS_NPU_MAX_PROMPT_LEN <= 512 )); then
        echo -e "${RED}ERROR: OVMS_NPU_MAX_PROMPT_LEN must be greater than 512 (got '${OVMS_NPU_MAX_PROMPT_LEN}').${NC}" >&2
        return 1
    fi
fi

# if only base environment variables are to be set without deploying application, exit here
if [ "$1" = "--setenv" ]; then
    echo -e  "${BLUE}Done setting up all environment variables. ${NC}"
    return 0
fi

# Set DRI_MOUNT_PATH based on whether /dev/dri exists and is not empty
if [ -d /dev/dri ] && [ "$(ls -A /dev/dri)" ]; then
    export DRI_MOUNT_PATH="/dev/dri"
    echo -e "${GREEN}/dev/dri found and not empty. Will mount.${NC}"
else
    export DRI_MOUNT_PATH="/dev/null"
    echo -e "${YELLOW}/dev/dri not found or empty, will mount /dev/null instead.${NC}"
fi

# Set ACCEL_MOUNT_PATH based on whether /dev/accel/accel0 exists (for NPU)
if [ -e /dev/accel/accel0 ]; then
    export ACCEL_MOUNT_PATH="/dev/accel/accel0"
    echo -e "${GREEN}/dev/accel/accel0 found. NPU device available and will be mounted.${NC}"
else
    export ACCEL_MOUNT_PATH="/dev/null"
    echo -e "${YELLOW}/dev/accel/accel0 not found, NPU not available. Will mount /dev/null instead.${NC}"
fi

# =================== Model Download Microservice (service mode) ===================
# Image auto-pulled by `docker run` if absent; --pull-always also refreshes a cached copy.
# Override MODEL_DOWNLOAD_IMAGE to pin a tag.
export MODEL_DOWNLOAD_IMAGE=${MODEL_DOWNLOAD_IMAGE:-intel/model-download:${MODEL_DOWNLOAD_TAG:-latest}}
# OVMS release tag used by the openvino plugin's export_model.py.
export MODEL_DOWNLOAD_OVMS_TAG=${MODEL_DOWNLOAD_OVMS_TAG:-v2026.4.1}
# Sub-path under the OVMS models dir for converted models (kept lowercase).
export OVMS_MS_DOWNLOAD_PATH=${OVMS_MS_DOWNLOAD_PATH:-ovms}
export MODEL_DOWNLOAD_HOST_PORT=${MODEL_DOWNLOAD_HOST_PORT:-8640}
MD_API_URL="http://127.0.0.1:${MODEL_DOWNLOAD_HOST_PORT}"
MD_NEED_OD=false; MD_NEED_VLM=false; MD_NEED_LLM=false

# curl wrapper for the model-download REST API. --noproxy keeps corporate proxy settings from intercepting loopback traffic.
md_curl() {
    curl -s --noproxy '*' --max-time 60 "$@"
}

# Render a seconds count as "3m41s" for status lines.
md_fmt_elapsed() {
    local total_seconds=$1
    printf '%dm%02ds' $((total_seconds / 60)) $((total_seconds % 60))
}

# Print one top-level field from a JSON document on stdin (empty if missing).
# Usage: ... | md_json_field <field>
md_json_field() {
    python3 -c 'import sys, json; print(json.load(sys.stdin).get(sys.argv[1]) or "")' "$1" 2>/dev/null
}

# Refresh a single in-place status line (TTY only); no text clears the line.
md_progress_line() {
    [ -t 1 ] && printf '\r\033[K%b' "${1:-}"
}

# True while the model-download container is running.
md_container_running() {
    [ "$(docker inspect -f '{{.State.Running}}' "${MODEL_DOWNLOAD_CTR_NAME}" 2>/dev/null)" = "true" ]
}

# Usage: md_start_service <plugins>
# ultralytics: object-detection model. openvino: VLM/LLM pull (OpenVINO/*) or HF->OVMS conversion.
md_start_service() {
    local plugins="$1"

    local env_args=(
        -e "MODEL_PATH=/opt/models"
        -e "HF_HUB_ENABLE_HF_TRANSFER=1"
        -e "OVMS_RELEASE_TAG=${MODEL_DOWNLOAD_OVMS_TAG}"
        -e "UV_CACHE_DIR=/opt/models/.model-download-cache/uv"
        -e "no_proxy=${no_proxy:-}"
        -e "http_proxy=${http_proxy:-}"
        -e "https_proxy=${https_proxy:-}"
    )
    local hf_token="${HUGGINGFACE_TOKEN:-${HUGGINGFACEHUB_API_TOKEN:-}}"
    if [ -n "$hf_token" ]; then
        env_args+=(-e "HF_TOKEN=${hf_token}")
    fi

    # Remove any leftover container from an interrupted earlier run.
    docker rm -f "${MODEL_DOWNLOAD_CTR_NAME}" >/dev/null 2>&1

    local pull_args=()
    [ "$vss_pull_always" = true ] && pull_args=(--pull always)

    mkdir -p "${OV_MODELS_ROOT}"
    echo -e "[model-download] ${BLUE}Starting model-download container (plugins: ${YELLOW}${plugins}${BLUE})${NC}"
    echo -e "[model-download] ${GRAY}API: ${MD_API_URL} ; follow detailed logs with: docker logs -f ${MODEL_DOWNLOAD_CTR_NAME}${NC}"
    if ! docker run -d "${pull_args[@]}" \
        --name "${MODEL_DOWNLOAD_CTR_NAME}" \
        -p "127.0.0.1:${MODEL_DOWNLOAD_HOST_PORT}:8000" \
        "${env_args[@]}" \
        -v "${OV_MODELS_ROOT}:/opt/models" \
        --group-add "$(id -g)" \
        "${MODEL_DOWNLOAD_IMAGE}" \
        --plugins "${plugins}" >/dev/null; then
        echo -e "${RED}ERROR: Could not start the model-download container.${NC}" >&2
        echo -e "${YELLOW}If port ${MODEL_DOWNLOAD_HOST_PORT} is busy, set MODEL_DOWNLOAD_HOST_PORT to a free port and re-run.${NC}" >&2
        return 1
    fi
    return 0
}

md_wait_healthy() {
    local started_at=$SECONDS
    echo -e "[model-download] ${YELLOW}Waiting for container to become healthy...${NC}"
    while true; do
        if md_curl -f "${MD_API_URL}/health" >/dev/null 2>&1; then
            md_progress_line ""
            echo -e "[model-download] ${GREEN}Container healthy ($(md_fmt_elapsed $((SECONDS - started_at))))${NC}"
            return 0
        fi
        if ! md_container_running; then
            md_progress_line ""
            echo -e "${RED}ERROR: model-download container exited before becoming healthy.${NC}" >&2
            return 1
        fi
        if [ $((SECONDS - started_at)) -ge 900 ]; then
            md_progress_line ""
            echo -e "${RED}ERROR: model-download container did not become healthy within 900s.${NC}" >&2
            return 1
        fi
        md_progress_line "[model-download] ${YELLOW}Waiting for container... ($(md_fmt_elapsed $((SECONDS - started_at))))${NC}"
        sleep 5
    done
}

md_payload_od() {
    printf '{"models":[{"name":"%s","hub":"ultralytics"}]}' "$1"
}

md_payload_ovms() {
    local model="$1" model_type="$2" device="$3" precision="$4" cache_size="$5" max_num_seqs="$6"
    local extra_config=""
    [ "$model_type" = "vlm" ] && extra_config=',"pipeline_type":"VLM_CB"'
    printf '{"models":[{"name":"%s","hub":"openvino","type":"%s","is_ovms":true,"config":{"precision":"%s","device":"%s","cache_size":%s,"max_num_seqs":%s%s}}]}' \
        "$model" "$model_type" "$precision" "$device" "$cache_size" "$max_num_seqs" "$extra_config"
}

# Submit one download job to the service; prints the job id on success.
# Usage: md_submit_job <download_path> <payload_json>
md_submit_job() {
    local download_path="$1"
    local payload="$2"
    local body_file http_code job_id

    body_file=$(mktemp)
    http_code=$(md_curl -o "$body_file" -w '%{http_code}' \
        -X POST "${MD_API_URL}/models/download?download_path=${download_path}" \
        -H 'Content-Type: application/json' \
        -d "$payload")
    if [ "$http_code" != "200" ]; then
        echo -e "${RED}ERROR: model-download job submission failed (HTTP ${http_code}): $(cat "$body_file")${NC}" >&2
        rm -f "$body_file"
        return 1
    fi

    job_id=$(python3 -c 'import sys, json; print(json.load(open(sys.argv[1]))["job_ids"][0])' "$body_file" 2>/dev/null)
    rm -f "$body_file"
    if [ -z "$job_id" ]; then
        echo -e "${RED}ERROR: model-download returned an unexpected response (no job id).${NC}" >&2
        return 1
    fi
    echo "$job_id"
}

# Wall-clock cap (seconds) for a single download/conversion job before setup.sh gives up.
export MODEL_DOWNLOAD_JOB_TIMEOUT=${MODEL_DOWNLOAD_JOB_TIMEOUT:-5400}

# Poll one job until it completes, printing a status line on each state change
md_wait_job() {
    local job_id="$1" label="$2"
    local state="queued" started_at=$SECONDS
    local job_json job_status job_error elapsed
    while true; do
        sleep 5
        if ! md_container_running; then
            md_progress_line ""
            echo -e "${RED}ERROR: model-download container stopped while a job was running.${NC}" >&2
            return 1
        fi

        if [ "${MODEL_DOWNLOAD_JOB_TIMEOUT}" -gt 0 ] 2>/dev/null && \
           [ $((SECONDS - started_at)) -ge "${MODEL_DOWNLOAD_JOB_TIMEOUT}" ]; then
            md_progress_line ""
            echo -e "[model-download] ${RED}${label}: TIMED OUT after $(md_fmt_elapsed $((SECONDS - started_at))) (last status: ${state:-unknown}).${NC}" >&2
            echo -e "${YELLOW}Increase MODEL_DOWNLOAD_JOB_TIMEOUT if this model legitimately needs longer.${NC}" >&2
            return 1
        fi

        job_json=$(md_curl "${MD_API_URL}/jobs/${job_id}")
        job_status=$(printf '%s' "$job_json" | md_json_field status)
        elapsed=$(md_fmt_elapsed $((SECONDS - started_at)))

        if [ "$job_status" = "completed" ]; then
            md_progress_line ""
            echo -e "[model-download] ${GREEN}${label}: completed (${elapsed})${NC}"
            return 0
        elif [ "$job_status" = "failed" ]; then
            job_error=$(printf '%s' "$job_json" | md_json_field error)
            md_progress_line ""
            echo -e "[model-download] ${RED}${label}: FAILED : ${job_error:-unknown error}${NC}" >&2
            return 1
        elif [ -n "$job_status" ] && [ "$job_status" != "$state" ]; then
            # An empty status is a transient API hiccup; retry next poll.
            md_progress_line ""
            echo -e "[model-download] ${YELLOW}${label}: ${job_status} (${elapsed})${NC}"
            state="$job_status"
        elif [ -n "$job_status" ]; then
            # Same state as before: tick the elapsed time so it doesn't look stuck.
            md_progress_line "[model-download] ${YELLOW}${label}: ${job_status} (${elapsed})${NC}"
        fi
    done
}

# Download one model: submit the job, then wait for it to finish.
# Usage: md_download_model <download_path> <payload_json> <label>
md_download_model() {
    local download_path="$1" payload="$2" label="$3"
    local job_id
    job_id=$(md_submit_job "$download_path" "$payload") || return 1
    echo -e "[model-download] ${BLUE}${label}: queued${NC}"
    md_wait_job "$job_id" "$label"
}

# Download one OVMS export: compute the cache size, build the payload, download.
# Usage: md_download_ovms_model <llm|vlm> <model> <device> <weight_format>
md_download_ovms_model() {
    local model_type="$1" model="$2" device="$3" weight_format="$4"
    local cache_size max_num_seqs
    cache_size=$(get_ovms_cache_size "$device") || return 1
    max_num_seqs=$(get_ovms_max_num_seqs)
    if [[ "${device^^}" == "NPU" ]]; then
        # NPU servables are stateful: OVMS ignores cache_size and max_num_seqs.
        echo -e "[ovms-service] ${BLUE}Device ${YELLOW}NPU${BLUE}: cache size and max_num_seqs do not apply${NC}"
    else
        echo -e "[ovms-service] ${BLUE}Cache size: ${YELLOW}${cache_size} GB${NC} for device ${YELLOW}${device}${NC}, max_num_seqs: ${YELLOW}${max_num_seqs}${NC}"
    fi
    md_download_model "${OVMS_MS_DOWNLOAD_PATH}" \
        "$(md_payload_ovms "$model" "$model_type" "$device" "$weight_format" "$cache_size" "$max_num_seqs")" \
        "${model_type^^} (${model})"
}

# Usage: md_teardown <rc>
md_teardown() {
    local rc=$1
    if [ "$rc" -ne 0 ]; then
        local log_file
        log_file="${OV_MODELS_ROOT}/model-download-$(date -u +%Y%m%dT%H%M%S.%NZ).log"
        docker logs "${MODEL_DOWNLOAD_CTR_NAME}" >"$log_file" 2>&1
        echo -e "${RED}ERROR: model download failed. Last log lines:${NC}" >&2
        tail -n 20 "$log_file" >&2 2>/dev/null
        echo -e "${YELLOW}Full log persisted at: ${log_file}${NC}" >&2
    fi
    docker rm -f "${MODEL_DOWNLOAD_CTR_NAME}" >/dev/null 2>&1
    return "$rc"
}

# Fix ownership of files written by the model-download container (runs as UID 1000):
fix_model_dir_ownership() {
    local host_dir="$1"
    [ -d "$host_dir" ] || return 0
    docker run --rm -u root \
        -v "${host_dir}:/target" \
        busybox sh -c "chown -R $(id -u):$(id -g) /target && chmod -R g+w /target && find /target -type d -exec chmod g+x {} +" 2>/dev/null || {
        echo -e "${YELLOW}WARNING: Could not fix ownership of ${host_dir}. Cache-size patching may fail.${NC}" >&2
    }
}

# Verify the expected object detection IR exists after download.
md_verify_od_model() {
    if [ -f "${OD_MODEL_OUTPUT_DIR}/FP32/${OD_MODEL_NAME}.xml" ]; then
        echo -e "[video-ingestion] ${GREEN}Object detection model ${OD_MODEL_NAME} ready at ${OD_MODEL_OUTPUT_DIR}/FP32/${NC}"
    else
        echo -e "${RED}ERROR: Expected IR not found at ${OD_MODEL_OUTPUT_DIR}/FP32/${OD_MODEL_NAME}.xml after download.${NC}" >&2
        return 1
    fi
}


# Compute the OVMS KV cache size (in GB) for a given target device.
#
# The KV cache stores intermediate attention state during LLM/VLM text
# generation. Its size must balance inference quality (larger = more
# concurrent/longer requests) against leaving enough memory for model
# weights and the OS.
#
# Allocation strategy per device type:
#   CPU  — 25% of system RAM, clamped to [2, 16] GB.
#          Model weights live in the same RAM so we cap at 16 GB to
#          leave headroom for weights + OS.
#   iGPU — 25% of system RAM, clamped to [2, 6] GB.
#          Integrated GPUs share system RAM with the OS and model
#          weights. The lower upper clamp (6 GB) prevents starving
#          the GPU driver's limited memory pool.
#   dGPU — 33% of dedicated VRAM, clamped to [2, 16] GB.
#          Discrete GPUs have their own VRAM, queried via the dmem
#          cgroup, xe tile sysfs, or lmem_total_bytes sysfs (i915 DKMS).
#          A higher percentage is safe because VRAM isn't shared with
#          the OS, but we still reserve ~67% for model weights.
#          If no VRAM is readable, an Intel GPU at PCI 0000:00:02.0 is
#          treated as the iGPU silently; any other Intel GPU triggers a
#          warning suggesting OVMS_CACHE_SIZE_GB.
#   NPU  — Not applicable; OVMS ignores cache_size for NPU stateful
#          servables, so this function does not handle NPU.
#
# Users can override all of this by exporting OVMS_CACHE_SIZE_GB.
get_ovms_cache_size() {
    local target_device="$1"
    # Allow user override via OVMS_CACHE_SIZE_GB environment variable (validated at startup)
    if [[ -n "${OVMS_CACHE_SIZE_GB:-}" ]]; then
        echo -e "[ovms-service] ${YELLOW}OVMS_CACHE_SIZE_GB is set, overriding dynamic cache size with ${OVMS_CACHE_SIZE_GB} GB${NC}" >&2
        echo "$OVMS_CACHE_SIZE_GB"
        return
    fi

    local total_ram_gb
    total_ram_gb=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)

    local cache_gb
    case "$target_device" in
        *GPU*)
            # Probe dedicated VRAM (xe driver: dmem cgroup; i915 DKMS: lmem sysfs) and
            # use 33% of it; if none found, assume iGPU and use 25% of shared system RAM.
            local vram_bytes=0
            if [[ -r /sys/fs/cgroup/dmem.capacity ]]; then
                vram_bytes=$(awk '$1 ~ /\/vram/ && $2 > max { max = $2 } END { print max + 0 }' \
                    /sys/fs/cgroup/dmem.capacity)
            fi

            # i915 DKMS: card*/lmem_total_bytes; xe: device/tile*/physical_vram_size_bytes.
            local lmem_file
            for lmem_file in /sys/class/drm/card*/lmem_total_bytes \
                             /sys/class/drm/card*/device/tile*/physical_vram_size_bytes; do
                [[ -f "$lmem_file" ]] || continue
                local v
                v=$(cat "$lmem_file" 2>/dev/null)
                if [[ -n "$v" && "$v" -gt "$vram_bytes" ]] 2>/dev/null; then
                    vram_bytes="$v"
                fi
            done

            if [[ "$vram_bytes" -gt 0 ]] 2>/dev/null; then
                # dGPU: ~33% of dedicated VRAM, clamped to [2, 16]
                local dgpu_vram_gb=$((vram_bytes / 1073741824))
                cache_gb=$((dgpu_vram_gb * 33 / 100))
                cache_gb=$(( cache_gb < 2 ? 2 : cache_gb > 16 ? 16 : cache_gb ))
            else
                # No dedicated VRAM found. Intel iGPUs always sit at PCI 0000:00:02.0, so
                # only warn when some other Intel GPU is present whose VRAM we couldn't read.
                local card card_dev unknown_gpu=false
                for card in /sys/class/drm/card*; do
                    [[ "${card##*/}" == *-* ]] && continue
                    card_dev=$(readlink -f "${card}/device" 2>/dev/null) || continue
                    [[ "$(cat "${card_dev}/vendor" 2>/dev/null)" == "0x8086" ]] || continue
                    [[ "${card_dev##*/}" == "0000:00:02.0" ]] || unknown_gpu=true
                done
                if [[ "$unknown_gpu" == true ]]; then
                    echo -e "[ovms-service] ${YELLOW}WARNING: Found a non-integrated Intel GPU but could not read its VRAM from sysfs; using the iGPU cache size.${NC}" >&2
                    echo -e "[ovms-service] ${YELLOW}         If '${target_device}' is a discrete GPU, set OVMS_CACHE_SIZE_GB to the correct value.${NC}" >&2
                fi
                # iGPU/shared memory: 25% of system RAM, clamped to [2, 6]
                cache_gb=$((total_ram_gb * 25 / 100))
                cache_gb=$(( cache_gb < 2 ? 2 : cache_gb > 6 ? 6 : cache_gb ))
            fi
            ;;
        *)
            # CPU: ~25% of system RAM, clamped to [2, 16]
            cache_gb=$((total_ram_gb * 25 / 100))
            cache_gb=$(( cache_gb < 2 ? 2 : cache_gb > 16 ? 16 : cache_gb ))
            ;;
    esac

    echo "$cache_gb"
}

# Get OVMS max_num_seqs (continuous-batching sequence cap) for graph.pbtxt.
# model-download defaults to 256, but hybrid linear-attention models (e.g.
# Qwen3.5) reserve fixed recurrent state per sequence inside the KV cache
# budget: Qwen3.5-4B needs ~25 MB/seq, so 256 seqs (~6.3 GB) overflow the
# 6 GB iGPU cache and OVMS fails with 'reserved_la_bytes <= budget_in_bytes'.
# Pipeline Manager never sends more than PM_VLM_CONCURRENT + PM_LLM_CONCURRENT
# requests at once (extra requests queue), so cap at that with a floor of 16.
# Users can override with OVMS_MAX_NUM_SEQS.
get_ovms_max_num_seqs() {
    if [[ -n "${OVMS_MAX_NUM_SEQS:-}" ]]; then
        echo "$OVMS_MAX_NUM_SEQS"
        return
    fi
    local pm_total=$(( ${PM_VLM_CONCURRENT:-0} + ${PM_LLM_CONCURRENT:-0} ))
    echo $(( pm_total > 16 ? pm_total : 16 ))
}

# Get weight format based on target device
# NPU and GPU require int4 for optimal performance
get_ovms_weight_format() {
    local target_device="$1"
    case "$target_device" in
        *NPU*|*GPU*)
            echo "int4"
            ;;
        *)
            echo "int8"
            ;;
    esac
}

sanitize_ovms_metadata_name() {
    printf '%s' "$1" | sed 's#[^A-Za-z0-9_.-]#_#g'
}

# Generate storage-aware model name that encodes device and weight format
# This allows multiple configurations of the same model to coexist
get_ovms_storage_model_name() {
    local source_model="$1"
    local target_device="$2"
    local weight_format="$3"
    local sanitized
    sanitized=$(sanitize_ovms_metadata_name "$source_model")
    
    # OpenVINO namespace models have fixed weight format baked into name
    # Only append device, not format
    if is_openvino_namespace_model "$source_model"; then
        printf '%s_%s' "$sanitized" "$target_device"
    else
        printf '%s_%s_%s' "$sanitized" "$target_device" "$weight_format"
    fi
}

# Function to reset OVMS config.json to only include specified models
# This ensures stale models from previous runs are removed
reset_ovms_config() {
    local ovms_model_config="${OV_MODELS_ROOT}/${OVMS_MS_DOWNLOAD_PATH}/config.json"
    local models_to_keep=("$@")

    if [ ! -f "${ovms_model_config}" ]; then
        return 0
    fi

    python3 - "$ovms_model_config" "${models_to_keep[@]}" <<'PY'
import json
import sys

config_path = sys.argv[1]
models_to_keep = set(sys.argv[2:])

try:
    with open(config_path, encoding="utf-8") as config_file:
        config = json.load(config_file)
except Exception:
    raise SystemExit(0)

if "model_config_list" not in config:
    raise SystemExit(0)

# Filter to only keep models that are in the models_to_keep set
original_count = len(config["model_config_list"])
config["model_config_list"] = [
    entry for entry in config["model_config_list"]
    if entry.get("config", {}).get("name") in models_to_keep
]
filtered_count = len(config["model_config_list"])

if filtered_count < original_count:
    with open(config_path, "w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=4)
    removed = original_count - filtered_count
    print(f"Removed {removed} stale model(s) from OVMS config")

raise SystemExit(0)
PY
}

# Check if model is from OpenVINO namespace (pre-converted, no conversion needed)
is_openvino_namespace_model() {
    [[ "$1" == OpenVINO/* ]]
}

# Host dir where the openvino plugin writes the converted OVMS model:
#   <models>/<download_path>/openvino_models/<device>/<precision>/<source_model>  (lowercased except source_model).
# The device segment must match model-download's path sanitization (main.py:
# re.sub(r"[^A-Za-z0-9._-]+", "_", device)), e.g. HETERO:GPU,CPU -> hetero_gpu_cpu.
ovms_ms_model_dir() {
    local source_model="$1"
    local target_device="$2"
    local weight_format="$3"
    local device_lc format_lc
    device_lc=$(printf '%s' "$target_device" | sed -E 's/[^A-Za-z0-9._-]+/_/g' | tr '[:upper:]' '[:lower:]')
    format_lc=$(printf '%s' "$weight_format" | tr '[:upper:]' '[:lower:]')
    printf '%s/%s/openvino_models/%s/%s/%s' \
        "${OV_MODELS_ROOT}" "${OVMS_MS_DOWNLOAD_PATH}" "${device_lc}" "${format_lc}" "${source_model}"
}

ovms_model_present() {
    local model_dir
    model_dir=$(ovms_ms_model_dir "$1" "$2" "$3")
    [ -f "${model_dir}/graph.pbtxt" ]
}

# OVMS loads a model directory as a VLM servable when it ships vision encoder IRs.
ovms_model_is_vlm() {
    [ -f "$1/openvino_vision_embeddings_model.xml" ]
}

# Set MAX_PROMPT_LEN / MIN_RESPONSE_LEN in the graph.pbtxt plugin_config of a
# text-only NPU LLM. OVMS's NPU LLM servable reads only the top-level keys
# (defaults 1024/128); DEVICE_PROPERTIES.NPU is updated too when present so the
# two never disagree. Exit status: 0 = already set, 10 = change needed (check
# mode), 1 = error.
ovms_npu_plugin_config() {
    python3 - "$1" "$2" "$OVMS_NPU_MAX_PROMPT_LEN" "$OVMS_NPU_MIN_RESPONSE_LEN" <<'PY'
import json, re, sys

path, mode, max_prompt, min_response = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
with open(path) as f:
    text = f.read()
match = re.search(r"plugin_config:\s*'([^']*)'", text)
if not match:
    print(f"plugin_config not found in {path}", file=sys.stderr)
    sys.exit(1)
try:
    current = json.loads(match.group(1) or "{}")
except json.JSONDecodeError as exc:
    print(f"plugin_config in {path} is not valid JSON: {exc}", file=sys.stderr)
    sys.exit(1)

limits = {"MAX_PROMPT_LEN": max_prompt, "MIN_RESPONSE_LEN": min_response}
updated = json.loads(json.dumps(current))
updated.update(limits)
npu_props = updated.get("DEVICE_PROPERTIES", {}).get("NPU")
if isinstance(npu_props, dict):
    npu_props.update(limits)
if updated == current:
    sys.exit(0)
if mode == "check":
    sys.exit(10)
with open(path, "w") as f:
    f.write(text[:match.start(1)] + json.dumps(updated, separators=(", ", ": ")) + text[match.end(1):])
PY
}

patch_ovms_npu_plugin_config() {
    local model_dir="$1" rc=0
    ovms_npu_plugin_config "${model_dir}/graph.pbtxt" check || rc=$?
    [ "$rc" -eq 0 ] && return 0
    if [ "$rc" -eq 10 ]; then
        fix_model_dir_ownership "${model_dir}"
        ovms_npu_plugin_config "${model_dir}/graph.pbtxt" write && rc=0 || rc=1
    fi
    if [ "$rc" -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to set NPU prompt limits in ${model_dir}/graph.pbtxt${NC}" >&2
        return 1
    fi
    echo -e "[ovms-service] ${BLUE}Set NPU limits: ${YELLOW}MAX_PROMPT_LEN=${OVMS_NPU_MAX_PROMPT_LEN}, MIN_RESPONSE_LEN=${OVMS_NPU_MIN_RESPONSE_LEN}${NC} in graph.pbtxt"
}

# NPU LLMs are compiled for a fixed prompt length: longer prompts are rejected
# and output past MAX_PROMPT_LEN + MIN_RESPONSE_LEN tokens is silently cut.
# Pipeline Manager budgets LLM input in characters, so convert the token limit
# at a conservative 2 chars/token (measured floor on VSS transcripts; summaries
# run ~4-5) after reserving 256 tokens for the chat template. The defaults are
# lowered to fit; explicit user values are kept but warned about.
apply_ovms_npu_llm_limits() {
    local derived_chars=$(( (OVMS_NPU_MAX_PROMPT_LEN - 256) * 2 ))
    if [ "$PM_LLM_MAX_CONTEXT_LENGTH_DEFAULTED" = true ]; then
        export PM_LLM_MAX_CONTEXT_LENGTH=$derived_chars
    elif ! [[ "$PM_LLM_MAX_CONTEXT_LENGTH" =~ ^[0-9]+$ ]] || (( PM_LLM_MAX_CONTEXT_LENGTH > derived_chars )); then
        echo -e "[ovms-service] ${YELLOW}WARNING: PM_LLM_MAX_CONTEXT_LENGTH=${PM_LLM_MAX_CONTEXT_LENGTH} exceeds the ~${derived_chars} chars that fit OVMS_NPU_MAX_PROMPT_LEN=${OVMS_NPU_MAX_PROMPT_LEN}; NPU may reject long summary prompts.${NC}" >&2
    fi
    if [ "$PM_SUMMARIZATION_MAX_COMPLETION_TOKENS_DEFAULTED" = true ]; then
        export PM_SUMMARIZATION_MAX_COMPLETION_TOKENS=$OVMS_NPU_MIN_RESPONSE_LEN
    elif ! [[ "$PM_SUMMARIZATION_MAX_COMPLETION_TOKENS" =~ ^[0-9]+$ ]] || (( PM_SUMMARIZATION_MAX_COMPLETION_TOKENS > OVMS_NPU_MIN_RESPONSE_LEN )); then
        echo -e "[ovms-service] ${YELLOW}WARNING: PM_SUMMARIZATION_MAX_COMPLETION_TOKENS=${PM_SUMMARIZATION_MAX_COMPLETION_TOKENS} exceeds OVMS_NPU_MIN_RESPONSE_LEN=${OVMS_NPU_MIN_RESPONSE_LEN}; NPU output may be cut short without notice.${NC}" >&2
    fi
    echo -e "[ovms-service] ${BLUE}NPU LLM limits - prompt: ${YELLOW}${OVMS_NPU_MAX_PROMPT_LEN}${BLUE} tokens (PM budget ${YELLOW}${PM_LLM_MAX_CONTEXT_LENGTH}${BLUE} chars), response: ${YELLOW}${PM_SUMMARIZATION_MAX_COMPLETION_TOKENS}${BLUE} tokens${NC}"
}

finalize_ovms_model() {
    local model="$1" target_device="$2" weight_format="$3"
    local model_dir storage_model_name desired_cache_size existing_cache_size
    local desired_max_num_seqs existing_max_num_seqs

    model_dir=$(ovms_ms_model_dir "$model" "$target_device" "$weight_format")
    if [ ! -f "${model_dir}/graph.pbtxt" ]; then
        echo -e "${RED}ERROR: Converted OVMS model not found at ${model_dir} (missing graph.pbtxt).${NC}" >&2
        return 1
    fi

    # Patch the KV cache size in graph.pbtxt if it differs from the desired one.
    desired_cache_size=$(get_ovms_cache_size "$target_device") || return 1
    existing_cache_size=$(sed -nE 's/.*cache_size:[[:space:]]*([0-9]+).*/\1/p' "${model_dir}/graph.pbtxt" 2>/dev/null | head -n 1)
    if [[ -n "$existing_cache_size" && "$existing_cache_size" -ne "$desired_cache_size" ]]; then
        fix_model_dir_ownership "${model_dir}"
        sed -i -E "s/cache_size:[[:space:]]*${existing_cache_size}/cache_size: ${desired_cache_size}/" "${model_dir}/graph.pbtxt" || {
            echo -e "${RED}ERROR: Failed to patch cache_size in ${model_dir}/graph.pbtxt${NC}" >&2
            return 1
        }
        echo -e "[ovms-service] ${BLUE}Updated cache size: ${YELLOW}${existing_cache_size} → ${desired_cache_size} GB${NC} in graph.pbtxt"
    fi

    # Patch max_num_seqs the same way (see get_ovms_max_num_seqs).
    desired_max_num_seqs=$(get_ovms_max_num_seqs)
    existing_max_num_seqs=$(sed -nE 's/.*max_num_seqs:[[:space:]]*([0-9]+).*/\1/p' "${model_dir}/graph.pbtxt" 2>/dev/null | head -n 1)
    if [[ -n "$existing_max_num_seqs" && "$existing_max_num_seqs" -ne "$desired_max_num_seqs" ]]; then
        fix_model_dir_ownership "${model_dir}"
        sed -i -E "s/max_num_seqs:[[:space:]]*${existing_max_num_seqs}/max_num_seqs: ${desired_max_num_seqs}/" "${model_dir}/graph.pbtxt" || {
            echo -e "${RED}ERROR: Failed to patch max_num_seqs in ${model_dir}/graph.pbtxt${NC}" >&2
            return 1
        }
        echo -e "[ovms-service] ${BLUE}Updated max_num_seqs: ${YELLOW}${existing_max_num_seqs} → ${desired_max_num_seqs}${NC} in graph.pbtxt"
    fi

    if [[ "${target_device^^}" == "NPU" ]]; then
        if ovms_model_is_vlm "$model_dir"; then
            # Raising MAX_PROMPT_LEN on an NPU VLM servable breaks every request
            # (OpenVINO 2026.4), and its 1024-token default is too small for the
            # final summary, so a VLM-type model cannot serve the LLM role on NPU.
            if [[ "$model" == "$LLM_MODEL_NAME" && "$target_device" == "$LLM_TARGET_DEVICE" && \
                  "$weight_format" == "$LLM_COMPRESSION_WEIGHT_FORMAT" ]]; then
                echo -e "${RED}ERROR: LLM_TARGET_DEVICE=NPU needs a text-only LLM, but ${model} is a vision-language model.${NC}" >&2
                echo -e "${YELLOW}Set OVMS_LLM_MODEL_NAME to a text-only model (e.g. OpenVINO/Phi-3.5-mini-instruct-int4-cw-ov) or set LLM_TARGET_DEVICE to GPU or CPU.${NC}" >&2
                return 1
            fi
        else
            patch_ovms_npu_plugin_config "$model_dir" || return 1
        fi
    fi

    # Register the model in OVMS config.json (add_model_to_ovms_config is idempotent).
    storage_model_name=$(get_ovms_storage_model_name "$model" "$target_device" "$weight_format")
    add_model_to_ovms_config "${OV_MODELS_ROOT}/${OVMS_MS_DOWNLOAD_PATH}/config.json" "${storage_model_name}" "${model_dir}"
}

# Decide what to do for one OVMS model: finalize it when already on disk,
# otherwise mark it for download by setting the given MD_NEED_* flag.
# model-download pulls an OpenVINO/* repo only when the repo's "cw" marker
# (NPU-optimized channel-wise int4) matches the device: NPU needs a "cw" repo and
# CPU/GPU need a non-"cw" one. On a mismatch it falls back to export_model.py,
# which cannot re-export OpenVINO/* repos ("Failed to download llm model"), so
# fail before starting the download.
# Usage: check_openvino_repo_device <model> <device>
check_openvino_repo_device() {
    local model="$1" device="$2"
    is_openvino_namespace_model "$model" || return 0
    local short_name="${model##*/}"
    if [[ "${device^^}" == "NPU" && "${short_name,,}" != *cw* ]]; then
        echo -e "[ovms-service] ${RED}ERROR: ${model} cannot be downloaded for NPU. For OpenVINO/* repos on NPU, model-download only pulls NPU-optimized channel-wise repos (name contains '-cw-'), for example OpenVINO/Phi-3.5-mini-instruct-int4-cw-ov or OpenVINO/Qwen3-8B-int4-cw-ov.${NC}" >&2
        return 1
    fi
    if [[ "${device^^}" != "NPU" && "${short_name,,}" == *cw* ]]; then
        echo -e "[ovms-service] ${RED}ERROR: ${model} is an NPU-optimized channel-wise repo and cannot be downloaded for ${device}. Use the same model without '-cw-' (for example ${model/-cw-/-}), or target NPU.${NC}" >&2
        return 1
    fi
}

md_finalize_or_queue_ovms() {
    local model="$1" device="$2" weight_format="$3" storage_name="$4" need_flag_var="$5"
    if ovms_model_present "$model" "$device" "$weight_format"; then
        echo -e "[ovms-service] ${GREEN}Model ${YELLOW}${storage_name}${GREEN} already exists. Skipping export.${NC}"
        finalize_ovms_model "$model" "$device" "$weight_format"
    else
        check_openvino_repo_device "$model" "$device" || return 1
        echo -e "[ovms-service] ${YELLOW}Model ${RED}${storage_name}${YELLOW} not found. Queueing download...${NC}"
        printf -v "$need_flag_var" '%s' true
    fi
}

# Helper to add a model to OVMS config.json
add_model_to_ovms_config() {
    local config_path="$1"
    local model_name="$2"
    local model_path="$3"
    local relative_path
    
    relative_path=$(realpath --relative-to="$(dirname "$config_path")" "$model_path")
    
    python3 - "$config_path" "$model_name" "$relative_path" <<'PY'
import json
import sys
import os

config_path, model_name, base_path = sys.argv[1:4]

if os.path.exists(config_path):
    with open(config_path, 'r') as f:
        config = json.load(f)
else:
    config = {"model_config_list": []}

# Check if model already exists
for model in config.get("model_config_list", []):
    if model.get("config", {}).get("name") == model_name:
        print(f"Model {model_name} already in config")
        sys.exit(0)

# Add new model
config.setdefault("model_config_list", []).append({
    "config": {"name": model_name, "base_path": base_path}
})

with open(config_path, 'w') as f:
    json.dump(config, f, indent=2)
print(f"Added {model_name} to config")
PY
}

# Download the object-detection model in its own transient container with only
# the ultralytics plugin, so its setup cannot block the OVMS downloads.
md_run_od_download() {
    md_start_service "ultralytics" || return 1
    md_wait_healthy || { md_teardown 1; return 1; }
    md_download_model "${OD_MODEL_DOWNLOAD_PATH}" "$(md_payload_od "$OD_MODEL_NAME")" \
        "Object Detection (${OD_MODEL_NAME})" || { md_teardown 1; return 1; }

    # The container writes as UID 1000; fix ownership before verifying the IR.
    local rc=0
    fix_model_dir_ownership "${OV_MODELS_ROOT}"
    md_verify_od_model || rc=1
    md_teardown "$rc"
}

# Download the VLM and/or LLM (one at a time, VLM first) in their own transient
# container with only the openvino plugin, then register them with OVMS.
md_run_ovms_downloads() {
    md_start_service "openvino" || return 1
    md_wait_healthy || { md_teardown 1; return 1; }
    if [ "$MD_NEED_VLM" = true ]; then
        md_download_ovms_model vlm "$VLM_MODEL_NAME" "$VLM_TARGET_DEVICE" \
            "$VLM_COMPRESSION_WEIGHT_FORMAT" || { md_teardown 1; return 1; }
    fi
    if [ "$MD_NEED_LLM" = true ]; then
        md_download_ovms_model llm "$LLM_MODEL_NAME" "$LLM_TARGET_DEVICE" \
            "$LLM_COMPRESSION_WEIGHT_FORMAT" || { md_teardown 1; return 1; }
    fi

    local rc=0
    fix_model_dir_ownership "${OV_MODELS_ROOT}"
    if [ "$MD_NEED_VLM" = true ]; then
        finalize_ovms_model "$VLM_MODEL_NAME" "$VLM_TARGET_DEVICE" "$VLM_COMPRESSION_WEIGHT_FORMAT" || rc=1
    fi
    if [ "$rc" -eq 0 ] && [ "$MD_NEED_LLM" = true ]; then
        finalize_ovms_model "$LLM_MODEL_NAME" "$LLM_TARGET_DEVICE" "$LLM_COMPRESSION_WEIGHT_FORMAT" || rc=1
    fi
    md_teardown "$rc"
}

# Download every model this run still needs (MD_NEED_OD / MD_NEED_VLM /
# MD_NEED_LLM). The OD and OVMS groups use separate containers and both are
# always attempted, so one group's failure does not block the other; a re-run
# only fetches what is still missing.
md_run_downloads() {
    local rc=0
    if [ "$MD_NEED_OD" = true ]; then
        md_run_od_download || rc=1
    fi
    if [ "$MD_NEED_VLM" = true ] || [ "$MD_NEED_LLM" = true ]; then
        md_run_ovms_downloads || rc=1
    fi
    return "$rc"
}

if [ "$1" = "--summary" ] || [ "$1" = "--search" ] || [ "$1" = "--dual" ] || [ "$1" = "--unified" ]; then
    APP_COMPOSE_FILE="-f docker/compose.base.yaml"
    export EMBEDDING_MODEL_NAME=${MULTIMODAL_EMBEDDING_MODEL}

    case "$1" in
        --summary)
            unset VS_INDEX_NAME
            export NGINX_UI_CONFIG="${nginx_config_dir}/singleton_ui.conf"
            export APP_FEATURE_MUX="ATOMIC"
            export APP_SUMMARY_FEATURE="FEATURE_ON"
            export APP_SEARCH_FEATURE="FEATURE_OFF"
            # Live RTSP ingestion writes to the search index, which this mode
            # does not deploy.
            export UI_LIVE_STREAMS_FEATURE="FEATURE_OFF"
            DEPLOYMENT_LABEL="Summary-only UI deployment. For summarizing video content."
            UI_PROFILE="singleton_summary_ui"
            APP_COMPOSE_FILE="${APP_COMPOSE_FILE} -f docker/compose.summary.yaml"
            ;;
        --search)
            export VS_INDEX_NAME="video_frame_embeddings"
            export NGINX_UI_CONFIG="${nginx_config_dir}/singleton_ui.conf"
            export APP_FEATURE_MUX="ATOMIC"
            export APP_SUMMARY_FEATURE="FEATURE_OFF"
            export APP_SEARCH_FEATURE="FEATURE_ON"
            # Live streams are a property of the mode, set unconditionally:
            # setup.sh is sourced, so a `:-` default would reuse a flag a prior
            # `--summary`/`--unified` left in the same shell and silently keep
            # live off here.
            export UI_LIVE_STREAMS_FEATURE="FEATURE_ON"
            export LIVE_STREAM_ENABLED="true"
            DEPLOYMENT_LABEL="Search-only UI deployment. For searching over video frame embeddings."
            UI_PROFILE="singleton_search_ui"
            APP_COMPOSE_FILE="${APP_COMPOSE_FILE} -f docker/compose.search.yaml"
            ;;
        --unified)
            export EMBEDDING_MODEL_NAME=${TEXT_EMBEDDING_MODEL}
            export VS_INDEX_NAME="video_summary_embeddings"
            export NGINX_UI_CONFIG="${nginx_config_dir}/singleton_ui.conf"
            export APP_FEATURE_MUX="SUMMARY_SEARCH"
            export APP_SUMMARY_FEATURE="FEATURE_ON"
            export APP_SEARCH_FEATURE="FEATURE_ON"
            # Unified mode indexes *summaries* with a text-only embedding
            # model, so dataprep here cannot embed live video frames. Live
            # stream ingestion is therefore unavailable in this mode. Disable
            # it in dataprep too, not just in the UI, so the /media/streams
            # API cannot accept a registration that could never succeed.
            export UI_LIVE_STREAMS_FEATURE="FEATURE_OFF"
            export LIVE_STREAM_ENABLED="false"
            DEPLOYMENT_LABEL="Unified single UI for summarization and searching. For searching over text embeddings of summaries."
            UI_PROFILE="singleton_unified_ui"
            APP_COMPOSE_FILE="${APP_COMPOSE_FILE} -f docker/compose.summary.yaml -f docker/compose.search.yaml"
            ;;
        --dual)
            export VS_INDEX_NAME="video_frame_embeddings"
            export NGINX_UI_CONFIG="${nginx_config_dir}/dual_ui.conf"
            export UI_LIVE_STREAMS_FEATURE="FEATURE_ON"
            export LIVE_STREAM_ENABLED="true"
            DEPLOYMENT_LABEL="Dual UI (Separate Summary and Search UI) deployment. For summarizing video content and searching over video frame embeddings."
            UI_PROFILE="dual_ui"
            APP_COMPOSE_FILE="${APP_COMPOSE_FILE} -f docker/compose.summary.yaml -f docker/compose.search.yaml"
            ;;
    esac

    APP_COMPOSE_FILE="${APP_COMPOSE_FILE} -f docker/compose.ui.yaml"
    APP_COMPOSE_FILE="${APP_COMPOSE_FILE} -f docker/compose.mcp.yaml"

    # Vector-DB backend overlay — applied only when the search path is active.
    # VDMS and Milvus each own their vector-DB container in a dedicated overlay
    # so that exactly one backend starts for a given VECTORDB_BACKEND.
    case "$APP_COMPOSE_FILE" in
        *docker/compose.search.yaml*)
            if [ "$VECTORDB_BACKEND" = "milvus" ]; then
                APP_COMPOSE_FILE="${APP_COMPOSE_FILE} -f docker/compose.search.milvus.yaml"
                vectordb_backend_label="Milvus"
            else
                APP_COMPOSE_FILE="${APP_COMPOSE_FILE} -f docker/compose.search.vdms.yaml"
                vectordb_backend_label="VDMS"
            fi
            ;;
        *)
            vectordb_backend_label=""
            ;;
    esac

    mkdir -p "${VS_WATCHER_DIR}" || return 1

    echo -e  "[pipeline-manager] ${GREEN}Setting up: ${DEPLOYMENT_LABEL}${NC}"
    if [ -n "${VS_INDEX_NAME}" ]; then
        echo -e  "[video-search] ${GREEN}Using vector-DB index: ${YELLOW}${VS_INDEX_NAME}${NC}"
    fi
    if [ -n "$vectordb_backend_label" ]; then
        echo -e  "[multimodal-dataprep] ${GREEN}Vector-DB backend: ${YELLOW}${vectordb_backend_label}${GREEN} (video-search delegates search to vector-retriever at ${YELLOW}${VS_RETRIEVER_ENDPOINT}${GREEN}).${NC}"
    fi
    echo -e  "[nginx] ${GREEN}Using UI routing config: ${YELLOW}${NGINX_UI_CONFIG}${NC}"
    if [ "$ENABLE_METRICS_MANAGER" = true ]; then
        case "$APP_COMPOSE_FILE" in
            *docker/compose.search.yaml*)
                APP_COMPOSE_FILE="$APP_COMPOSE_FILE -f docker/compose.metrics-manager.yaml"
                echo -e  "[metrics-manager] ${GREEN}Metrics Manager enabled ${NC}"
                ;;
            *)
                echo -e  "[metrics-manager] ${YELLOW}Metrics Manager requires a search-enabled mode; ignoring ENABLE_METRICS_MANAGER for summary-only mode${NC}"
                ;;
        esac
    else
        echo -e  "[metrics-manager] ${YELLOW}Metrics Manager disabled (set ENABLE_METRICS_MANAGER=true to enable)${NC}"
    fi

    # Validate expected OpenVINO artifact; directory-only checks can miss partial/incomplete model state.
    od_model_xml="${OD_MODEL_OUTPUT_DIR}/FP32/${OD_MODEL_NAME}.xml"
    od_model_bin="${OD_MODEL_OUTPUT_DIR}/FP32/${OD_MODEL_NAME}.bin"
    if [ "$1" != "--search" ] && [ "$2" != "config" ]; then
        if [ ! -f "${od_model_xml}" ] || [ ! -f "${od_model_bin}" ]; then
            echo -e  "[video-ingestion] ${YELLOW}Object detection model file not found at ${od_model_xml} or ${od_model_bin}. Queueing model download...${NC}"
            mkdir -p "${OD_MODEL_OUTPUT_DIR}"
            MD_NEED_OD=true
        else
            echo -e  "[video-ingestion] ${YELLOW}Object detection model file found at ${od_model_xml}. Skipping model setup...${NC}"
        fi
    fi

    configured_ovms_llm_model=${OVMS_LLM_MODEL_NAME:-}
    BACKEND_PROFILE="ovms"

    if [ "$1" != "--search" ]; then
        if [ "$ENABLE_VLLM_GPU" = true ]; then
            echo -e "[vllm-xpu-service] ${BLUE}Using vLLM on XPU/GPU for both chunk captioning and final summary${NC}"
            echo -e "[vllm-xpu-service] ${YELLOW}Disabling OVMS because ENABLE_VLLM_GPU=true${NC}"
            BACKEND_PROFILE="vllm-xpu"
            if [ -n "$configured_ovms_llm_model" ] && [ "$configured_ovms_llm_model" != "$VLM_MODEL_NAME" ]; then
                echo -e "[pipeline-manager] ${YELLOW}Ignoring separate OVMS LLM model in vLLM-only mode; summarization will use VLM_MODEL_NAME=${VLM_MODEL_NAME}${NC}"
            fi
            export LLM_MODEL_NAME=${VLM_MODEL_NAME}
            if [ "$PM_VLM_CONCURRENT_DEFAULTED" = true ]; then
                export PM_VLM_CONCURRENT=1
            fi
            if [ "$PM_LLM_CONCURRENT_DEFAULTED" = true ]; then
                export PM_LLM_CONCURRENT=1
            fi
            if [ "$PM_CAPTIONING_MAX_COMPLETION_TOKENS_DEFAULTED" = true ]; then
                export PM_CAPTIONING_MAX_COMPLETION_TOKENS=256
            fi
            APP_COMPOSE_FILE="$APP_COMPOSE_FILE -f docker/compose.vllm.xpu.yaml"
        elif [ "$ENABLE_VLLM" = true ]; then
            echo -e "[vllm-cpu-service] ${BLUE}Using vLLM for both chunk captioning and final summary${NC}"
            BACKEND_PROFILE="vllm"
            if [ -n "$configured_ovms_llm_model" ] && [ "$configured_ovms_llm_model" != "$VLM_MODEL_NAME" ]; then
                echo -e "[pipeline-manager] ${YELLOW}Ignoring separate OVMS LLM model in vLLM-only mode; summarization will use VLM_MODEL_NAME=${VLM_MODEL_NAME}${NC}"
            fi
            export LLM_MODEL_NAME=${VLM_MODEL_NAME}
            if [ "$PM_VLM_CONCURRENT_DEFAULTED" = true ]; then
                export PM_VLM_CONCURRENT=1
            fi
            if [ "$PM_LLM_CONCURRENT_DEFAULTED" = true ]; then
                export PM_LLM_CONCURRENT=1
            fi
            if [ "$PM_CAPTIONING_MAX_COMPLETION_TOKENS_DEFAULTED" = true ]; then
                export PM_CAPTIONING_MAX_COMPLETION_TOKENS=256
            fi
            APP_COMPOSE_FILE="$APP_COMPOSE_FILE -f docker/compose.vllm.yaml"
        else
            echo -e "[ovms-service] ${BLUE}Using OVMS for both chunk captioning and final summary${NC}"
            APP_COMPOSE_FILE="$APP_COMPOSE_FILE -f docker/compose.ovms.yaml"
            export LLM_MODEL_NAME=${configured_ovms_llm_model:-${VLM_MODEL_NAME}}

            # VLM_TARGET_DEVICE supports CPU, GPU, HETERO:...; LLM_TARGET_DEVICE also supports NPU
            # (defaults already set at top of script)
            if [ -z "$configured_ovms_llm_model" ]; then
                if [ "$LLM_TARGET_DEVICE_DEFAULTED" = true ]; then
                    export LLM_TARGET_DEVICE="$VLM_TARGET_DEVICE"
                fi
                if [ -z "$LLM_COMPRESSION_WEIGHT_FORMAT" ] && [ -n "$VLM_COMPRESSION_WEIGHT_FORMAT" ]; then
                    export LLM_COMPRESSION_WEIGHT_FORMAT="$VLM_COMPRESSION_WEIGHT_FORMAT"
                fi
            fi

            # Determine weight format: user override takes precedence, otherwise auto-detect based on device
            export VLM_COMPRESSION_WEIGHT_FORMAT=${VLM_COMPRESSION_WEIGHT_FORMAT:-$(get_ovms_weight_format "$VLM_TARGET_DEVICE")}
            export LLM_COMPRESSION_WEIGHT_FORMAT=${LLM_COMPRESSION_WEIGHT_FORMAT:-$(get_ovms_weight_format "$LLM_TARGET_DEVICE")}

            use_openvino_model_weight_format "VLM" "$VLM_MODEL_NAME" "VLM_COMPRESSION_WEIGHT_FORMAT" || return 1
            use_openvino_model_weight_format "LLM" "$LLM_MODEL_NAME" "LLM_COMPRESSION_WEIGHT_FORMAT" || return 1

            enforce_npu_int4_weight_format "VLM" "$VLM_TARGET_DEVICE" "VLM_COMPRESSION_WEIGHT_FORMAT"
            enforce_npu_int4_weight_format "LLM" "$LLM_TARGET_DEVICE" "LLM_COMPRESSION_WEIGHT_FORMAT"

            echo -e "[ovms-service] ${BLUE}Target device - VLM: ${YELLOW}${VLM_TARGET_DEVICE}${BLUE} (${VLM_COMPRESSION_WEIGHT_FORMAT}), LLM: ${YELLOW}${LLM_TARGET_DEVICE}${BLUE} (${LLM_COMPRESSION_WEIGHT_FORMAT})${NC}"

            if [[ "${LLM_TARGET_DEVICE^^}" == "NPU" ]]; then
                apply_ovms_npu_llm_limits
            fi

            # Concurrency keeps the global defaults (VLM 4, LLM 2) on every OVMS device;
            # only the per-request frame count is reduced for non-CPU devices.
            if [[ "$VLM_TARGET_DEVICE" != "CPU" ]]; then
                if [ "$PM_MULTI_FRAME_COUNT_DEFAULTED" = true ]; then
                    export PM_MULTI_FRAME_COUNT=6
                fi
            fi

            # Add GPU compose override if either device uses GPU
            if [[ "$VLM_TARGET_DEVICE" == *"GPU"* ]] || [[ "$LLM_TARGET_DEVICE" == *"GPU"* ]]; then
                echo -e "[ovms-service] ${BLUE}Using GPU-capable OVMS image${NC}"
                APP_COMPOSE_FILE="$APP_COMPOSE_FILE -f docker/compose.gpu_ovms.yaml"
            fi

            ovms_split_model=false
            # Use split-model mode whenever VLM and LLM effective settings differ:
            # model source, target device, or compression format.
            if [ -n "$LLM_MODEL_NAME" ] && {
                [ "$LLM_MODEL_NAME" != "$VLM_MODEL_NAME" ] || \
                [ "$LLM_TARGET_DEVICE" != "$VLM_TARGET_DEVICE" ] || \
                [ "$LLM_COMPRESSION_WEIGHT_FORMAT" != "$VLM_COMPRESSION_WEIGHT_FORMAT" ];
            }; then
                ovms_split_model=true
                echo -e "[ovms-service] ${BLUE}Using split-model OVMS mode: VLM=${VLM_MODEL_NAME} (${VLM_TARGET_DEVICE}, ${VLM_COMPRESSION_WEIGHT_FORMAT}), LLM=${LLM_MODEL_NAME} (${LLM_TARGET_DEVICE}, ${LLM_COMPRESSION_WEIGHT_FORMAT})${NC}"
            else
                echo -e "[ovms-service] ${BLUE}Using shared single-model OVMS mode with VLM=${VLM_MODEL_NAME}${NC}"
            fi

            # Compute storage model names that encode device and format
            # These are exported for pipeline-manager to use when calling OVMS API
            export VLM_STORAGE_MODEL_NAME
            VLM_STORAGE_MODEL_NAME=$(get_ovms_storage_model_name "$VLM_MODEL_NAME" "$VLM_TARGET_DEVICE" "$VLM_COMPRESSION_WEIGHT_FORMAT")
            
            if [ "$ovms_split_model" = true ]; then
                export LLM_STORAGE_MODEL_NAME
                LLM_STORAGE_MODEL_NAME=$(get_ovms_storage_model_name "$LLM_MODEL_NAME" "$LLM_TARGET_DEVICE" "$LLM_COMPRESSION_WEIGHT_FORMAT")
            else
                export LLM_STORAGE_MODEL_NAME="$VLM_STORAGE_MODEL_NAME"
            fi
            
            echo -e "[ovms-service] ${GREEN}Storage models - VLM: ${YELLOW}${VLM_STORAGE_MODEL_NAME}${GREEN}, LLM: ${YELLOW}${LLM_STORAGE_MODEL_NAME}${NC}"

            if [ "$2" != "config" ]; then
                # Reset OVMS config to only include storage model names needed for this run
                if [ "$ovms_split_model" = true ]; then
                    reset_ovms_config "$VLM_STORAGE_MODEL_NAME" "$LLM_STORAGE_MODEL_NAME"
                else
                    reset_ovms_config "$VLM_STORAGE_MODEL_NAME"
                fi

                # Models already on disk are finalized right away; missing ones
                # are queued for md_run_downloads below.
                md_finalize_or_queue_ovms "$VLM_MODEL_NAME" "$VLM_TARGET_DEVICE" \
                    "$VLM_COMPRESSION_WEIGHT_FORMAT" "$VLM_STORAGE_MODEL_NAME" MD_NEED_VLM || return 1
                if [ "$ovms_split_model" = true ]; then
                    md_finalize_or_queue_ovms "$LLM_MODEL_NAME" "$LLM_TARGET_DEVICE" \
                        "$LLM_COMPRESSION_WEIGHT_FORMAT" "$LLM_STORAGE_MODEL_NAME" MD_NEED_LLM || return 1
                fi
            fi
        fi
    fi

    # Download any models still missing before bringing the application up.
    if [ "$2" != "config" ]; then
        md_run_downloads || return 1
    fi

    # if config is passed, set the command to only generate the config
    FINAL_ARGS=(up -d)
    [ "$vss_pull_always" = true ] && FINAL_ARGS+=(--pull always)
    [ "$2" = "config" ] && FINAL_ARGS=(config)
    # Overlay paths above are fixed tokens, never shell commands.
    read -r -a COMPOSE_ARGS <<< "$APP_COMPOSE_FILE"
    DOCKER_COMMAND=(docker compose "${COMPOSE_ARGS[@]}" --profile "$BACKEND_PROFILE" --profile "$UI_PROFILE" --profile mcp "${FINAL_ARGS[@]}")
fi

# Run the Docker command to set up the application
if [ "${#DOCKER_COMMAND[@]}" -gt 0 ]; then
    echo -e  "${GREEN}Running Docker command: ${DOCKER_COMMAND[*]} ${NC}"
    "${DOCKER_COMMAND[@]}"
else
    echo -e  "No valid setup command provided. Please run with --help option to see available commands."
fi
if [ $? -ne 0 ]; then
    echo -e "\n${RED}Failed: Some error occured while setting up one or more containers.${NC}" >&2
    return 1
fi
if [ "$2" !=  "config" ]; then
    echo -e "\n${GREEN}Setup completed successfully! 😎"
    if [ "$1" = "--dual" ]; then
        echo -e "Two UI instances are now available:"
        echo -e "  • ${BLUE}Video Summarization UI:${NC} ${YELLOW}http://${HOST_IP}:${APP_HOST_PORT}/summary/${NC}"
        echo -e "  • ${BLUE}Video Search UI:       ${NC} ${YELLOW}http://${HOST_IP}:${APP_HOST_PORT}/search/${NC}"
        echo -e "${GRAY}Note: Root URL http://${HOST_IP}:${APP_HOST_PORT}/ redirects to Summary UI.${NC}"
    elif [ "$1" = "--unified" ]; then
        echo -e "Unified Summarization/Search UI is now available at: ${YELLOW}http://${HOST_IP}:${APP_HOST_PORT}/${NC}"
    elif [ "$1" = "--summary" ]; then
        echo -e "Video Summarization UI is now available at: ${YELLOW}http://${HOST_IP}:${APP_HOST_PORT}/${NC}"
    elif [ "$1" = "--search" ]; then
        echo -e "Video Search UI is now available at: ${YELLOW}http://${HOST_IP}:${APP_HOST_PORT}/${NC}"
    fi
    echo -e "${GREEN}VSS MCP server (Streamable HTTP):${NC} ${YELLOW}http://${HOST_IP}:${APP_HOST_PORT}/mcp${NC}"
fi

# Reset all position arguments overrides
set --
