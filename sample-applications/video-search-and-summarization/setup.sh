#!/bin/bash
# Copyright (C) 2026 Intel Corporation
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
# Host root for all OpenVINO model assets — holds both the object-detection IRs
# and the OVMS converted models + config.json (written by the model-download
# microservice).
export OV_MODELS_ROOT="${PWD}/ov_models"

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

# =================== Function Definitions =========================
stop_containers() {
    echo -e "${YELLOW}Bringing down all the Docker containers... ${NC}"
    docker compose \
        -f docker/compose.base.yaml \
        -f docker/compose.summary.yaml \
        -f docker/compose.vllm.yaml \
        -f docker/compose.vllm.xpu.yaml \
        -f docker/compose.search.yaml \
        -f docker/compose.ui.yaml \
        -f docker/compose.telemetry.yaml \
        --profile ovms --profile vlm-ov --profile vllm --profile vllm-xpu \
        --profile dual_ui --profile singleton_unified_ui \
        --profile singleton_summary_ui \
        --profile singleton_search_ui \
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
    docker volume rm docker_minio_data docker_pg_data docker_vdms-db docker_audio_analyzer_data docker_data-prep docker_collector_signals 2>/dev/null
    if [ $? -ne 0 ]; then
        echo -e "${YELLOW}Note: Could not remove all volumes. Some volumes may not have existed, were already removed or currently in use. ${NC}"
        return 0
    fi
    echo -e "${GREEN}All volumes were successfully removed. ${NC}"
    return 0
}

show_concise_help() {
    echo -e "Video Search and Summarization Application setup script v1.0"
    echo -e "Copyright (C) 2026 Intel Corporation"
    echo -e "${YELLOW}USAGE: ${GREEN}source setup.sh ${BLUE}--summary [--search] | --search [--summary] | --search-and-summary | --stop | --clean-data | config ${NC}"
    echo -e "${YELLOW}EXAMPLES:"
    echo -e "${GRAY}source setup.sh --summary"
    echo -e "source setup.sh --search"
    echo -e "source setup.sh --summary --search${NC}"
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

show_full_help() {
    echo -e  "-----------------------------------------------------------------"
    echo -e  "${YELLOW}USAGE: ${GREEN}source setup.sh ${BLUE}[ --summary [--search] [config] | --search [--summary] [config] | --search-and-summary [config] |"
    echo -e  "                         --stop | --clean-data | --set-env | --help ]"
    echo -e  "${YELLOW}"
    echo -e  "                -h, --help:  Shows this help message."
    echo -e  "                 --summary:  Deploy Video Summary Application."
    echo -e  "                             ${GRAY}Use with ${GREEN}--search${GRAY} option to deploy both summary and search applications together.${NC}"
    echo -e "${YELLOW}                  --search:  Deploy Video Search Application."
    echo -e  "                             ${GRAY}Use with ${GREEN}--summary${GRAY} option to deploy both search and summary applications together.${NC}"
    echo -e  "${YELLOW}      --summary-and-search:  Deploy a modified Video Search application which does video summarization first and searches on summary content."
    echo -e  "                  --setenv:  Set environment variables without setting up application or starting any containers."
    echo -e  "            --down, --stop:  Bring down all the docker containers for the application."
    echo -e  "              --clean-data:  Bring down all the docker containers and remove all docker volumes for the user data."
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
export HOST_IP=$(ip route get 1 | awk '{print $7}')  # Fetch the host IP
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
export PM_SUMMARIZATION_MAX_COMPLETION_TOKENS=${PM_SUMMARIZATION_MAX_COMPLETION_TOKENS:-4000}
PM_CAPTIONING_MAX_COMPLETION_TOKENS_DEFAULTED=false
if [[ -z "${PM_CAPTIONING_MAX_COMPLETION_TOKENS+x}" ]]; then
    export PM_CAPTIONING_MAX_COMPLETION_TOKENS=1024
    PM_CAPTIONING_MAX_COMPLETION_TOKENS_DEFAULTED=true
fi
export PM_LLM_MAX_CONTEXT_LENGTH=${PM_LLM_MAX_CONTEXT_LENGTH:-90000}
PM_LLM_CONCURRENT_DEFAULTED=false
if [[ -z "${PM_LLM_CONCURRENT+x}" ]]; then
    export PM_LLM_CONCURRENT=2
    PM_LLM_CONCURRENT_DEFAULTED=true
fi
PM_VLM_CONCURRENT_DEFAULTED=false
if [[ -z "${PM_VLM_CONCURRENT+x}" ]]; then
    export PM_VLM_CONCURRENT=4
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

# env for rabbitmq
export RABBITMQ_USER=${RABBITMQ_USER}  # Set this in your shell before running the script
export RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD} # Set this in your shell before running the script

# env for postgres
export POSTGRES_USER=${POSTGRES_USER}  # Set this in your shell before running the script
export POSTGRES_PASSWORD=${POSTGRES_PASSWORD}  # Set this in your shell before running the script

# env for minio-service
export MINIO_ROOT_USER=${MINIO_ROOT_USER} # Set this in your shell before running the script
export MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD} # Set this in your shell before running the script

# Embedding processing mode settings (SDK vs API)
# EMBEDDING_PROCESSING_MODE options:
#   - "sdk": Use multimodal embedding service directly as SDK (optimized approach with better memory usage, default)
#   - "api": Use HTTP API calls to multimodal embedding service (existing approach)
export EMBEDDING_PROCESSING_MODE=${EMBEDDING_PROCESSING_MODE:-"sdk"}

export EMBEDDING_USE_OV=${EMBEDDING_USE_OV:-$SDK_USE_OPENVINO}
# Per-component device selection (CPU default | GPU | NPU). Each component is
# independent — parity with the Helm charts. No "baseline" device.
#   DATAPREP_EMBEDDING_DEVICE → embedding in vdms-dataprep (EMBEDDING_PROCESSING_MODE=sdk)
#   DATAPREP_DETECTION_DEVICE → YOLOX object detection in vdms-dataprep
#   MME_EMBEDDING_DEVICE      → embedding in multimodal-embedding-serving (EMBEDDING_PROCESSING_MODE=api)
export DATAPREP_EMBEDDING_DEVICE=${DATAPREP_EMBEDDING_DEVICE:-"CPU"}
export DATAPREP_DETECTION_DEVICE=${DATAPREP_DETECTION_DEVICE:-"CPU"}
export MME_EMBEDDING_DEVICE=${MME_EMBEDDING_DEVICE:-"CPU"}

# Device Configuration
export SDK_USE_OPENVINO=${SDK_USE_OPENVINO:-true}

# Easy-button: put embedding on GPU. Mode-aware — targets the component that
# actually runs embedding in the active EMBEDDING_PROCESSING_MODE.
if [ "$ENABLE_EMBEDDING_GPU" = true ]; then
    if [ "${EMBEDDING_PROCESSING_MODE}" = "api" ]; then
        export MME_EMBEDDING_DEVICE=GPU
    else
        export DATAPREP_EMBEDDING_DEVICE=GPU
    fi
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
        fi
        if [[ ! -d "/dev/dri" ]]; then
            echo -e "${RED}Warning: /dev/dri not found. GPU acceleration may not be available.${NC}" >&2
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
    export VDMS_DATAPREP_DEVICE="${device}"
    echo -e "[vdms-dataprep] ${BLUE}Processing device: ${YELLOW}${device}${NC} (video decoding, object detection, embedding)"
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

if [ $1 != "--summary" ]; then
    if [ "$1" = "--unified" ]; then
        embedding_model_display="${TEXT_EMBEDDING_MODEL:-"(not provided)"}"
    else
        embedding_model_display="${MULTIMODAL_EMBEDDING_MODEL:-"(not provided)"}"
    fi
    # sdk mode runs embeddings in-process within vdms-dataprep; api mode routes
    # them over HTTP to the multimodal-embedding-serving container.
    echo -e "[vdms-dataprep] ${BLUE}Embedding: mode ${YELLOW}${EMBEDDING_PROCESSING_MODE}${BLUE}, model ${YELLOW}${embedding_model_display}${BLUE}, device ${YELLOW}${EMBEDDING_DEVICE}${NC}"
fi

# env for video-search
export VS_WATCHER_DIR=${VS_WATCHER_DIR:-$PWD/data}

# Telemetry collector toggle for search (disabled by default)
export ENABLE_VSS_COLLECTOR=${ENABLE_VSS_COLLECTOR:-false}

# Object detection model (ultralytics hub id; converted to OpenVINO IR by the
# model-download microservice). Required for all modes except --search;
# validated below with the other required environment variables.
export OD_MODEL_NAME=${OD_MODEL_NAME}
# Default object detection model; used as fallback for unsupported selections.
OD_MODEL_DEFAULT="yolov8l"
if [ "$1" != "--search" ]; then
    # yolov8l-worldv2 (open-vocabulary YOLO-World) is not supported by the
    # object-detection pipeline. Warn and fall back to the default model.
    if [ "$OD_MODEL_NAME" = "yolov8l-worldv2" ]; then
        echo -e "[video-ingestion] ${YELLOW}Warning: object detection model '${RED}${OD_MODEL_NAME}${YELLOW}' is not supported. Falling back to the default model '${GREEN}${OD_MODEL_DEFAULT}${YELLOW}'.${NC}" >&2
        export OD_MODEL_NAME="$OD_MODEL_DEFAULT"
    fi
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
    if [ "$1" = "--search" ] || [ "$1" = "--dual" ]; then
        require_env MULTIMODAL_EMBEDDING_MODEL "This is required for both SDK and API embedding modes for Video Search." || return 1
    fi

    # Validate embedding processing mode
    if [[ "$EMBEDDING_PROCESSING_MODE" != "api" && "$EMBEDDING_PROCESSING_MODE" != "sdk" ]]; then
        echo -e "${RED}Invalid EMBEDDING_PROCESSING_MODE: $EMBEDDING_PROCESSING_MODE${NC}" >&2
        echo -e "${YELLOW}Valid options are: 'api' or 'sdk'${NC}" >&2
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

# =================== Model Download Microservice (ephemeral) ===================
# Image auto-pulled by `docker run` if absent. Override MODEL_DOWNLOAD_IMAGE to pin a tag.
export MODEL_DOWNLOAD_TAG=${MODEL_DOWNLOAD_TAG:-${TAG:-latest}}
export MODEL_DOWNLOAD_IMAGE=${MODEL_DOWNLOAD_IMAGE:-intel/model-download:${MODEL_DOWNLOAD_TAG}}
# OVMS release tag used by the openvino plugin's export_model.py.
export MODEL_DOWNLOAD_OVMS_TAG=${MODEL_DOWNLOAD_OVMS_TAG:-v2026.1}
# Sub-path under the OVMS models dir for converted models (kept lowercase).
export OVMS_MS_DOWNLOAD_PATH=${OVMS_MS_DOWNLOAD_PATH:-ovms}

# One-shot (ephemeral) model download+convert via the microservice container.
# Usage: download_model_via_ms <host_models_dir> <plugins> [get_model.sh args...]
download_model_via_ms() {
    local host_models_dir="$1"; shift
    local plugins="$1"; shift

    if [ -z "$host_models_dir" ] || [ -z "$plugins" ]; then
        echo -e "${RED}ERROR: download_model_via_ms requires <host_models_dir> and <plugins>.${NC}" >&2
        return 1
    fi

    mkdir -p "$host_models_dir"

    local env_args=(
        -e "ENABLED_PLUGINS=${plugins}"
        -e "MODEL_PATH=/opt/models"
        -e "HF_HUB_ENABLE_HF_TRANSFER=1"
        -e "OVMS_RELEASE_TAG=${MODEL_DOWNLOAD_OVMS_TAG}"
        -e "no_proxy=${no_proxy:-}"
        -e "http_proxy=${http_proxy:-}"
        -e "https_proxy=${https_proxy:-}"
    )

    local hf_token="${HUGGINGFACE_TOKEN:-${HUGGINGFACEHUB_API_TOKEN:-}}"
    if [ -n "$hf_token" ]; then
        env_args+=(-e "HF_TOKEN=${hf_token}")
    fi
    
    local log_file="${host_models_dir}/model-download.log"

    echo -e "[model-download] ${BLUE}Running ${YELLOW}${MODEL_DOWNLOAD_IMAGE}${BLUE} (plugins: ${plugins}) — image auto-pulls if absent...${NC}"
    echo -e "[model-download] ${GRAY}This may take a while. Output is logged to ${log_file}${NC}"
    docker run --rm \
        "${env_args[@]}" \
        -v "${host_models_dir}:/opt/models" \
        --group-add "$(id -g)" \
        "${MODEL_DOWNLOAD_IMAGE}" \
        --plugins "${plugins}" --ephemeral "$@" >"$log_file" 2>&1
    local rc=$?

    if [ $rc -eq 0 ]; then
        rm -f "$log_file"
    else
        echo -e "${RED}ERROR: model-download failed (exit code ${rc}). Last log lines:${NC}" >&2
        tail -n 20 "$log_file" >&2 2>/dev/null
        echo -e "${YELLOW}Full log persisted at: ${log_file}${NC}" >&2
    fi
    return $rc
}

# Fix ownership of files written by the model-download container (runs as UID 1001):
# chown back to the host user and add group-write so re-downloads still work.
fix_model_dir_ownership() {
    local host_dir="$1"
    [ -d "$host_dir" ] || return 0
    docker run --rm -u root \
        -v "${host_dir}:/target" \
        busybox sh -c "chown -R $(id -u):$(id -g) /target && chmod -R g+w /target && find /target -type d -exec chmod g+x {} +" 2>/dev/null || {
        echo -e "${YELLOW}WARNING: Could not fix ownership of ${host_dir}. Cache-size patching may fail.${NC}" >&2
    }
}

# Download & convert the object detection model via the model-download
# microservice (ultralytics plugin -> OpenVINO IR, FP16 + FP32).
convert_object_detection_models() {
    echo -e "[video-ingestion] ${BLUE}Downloading & converting object detection model '${OD_MODEL_NAME}' via model-download microservice...${NC}"

    download_model_via_ms \
        "${OV_MODELS_ROOT}" \
        "ultralytics" \
        --model-name "${OD_MODEL_NAME}" \
        --hub ultralytics \
        --download-path "${OD_MODEL_DOWNLOAD_PATH}"

    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Model download/conversion failed for ${OD_MODEL_NAME}.${NC}" >&2
        return 1
    fi

    fix_model_dir_ownership "${OV_MODELS_ROOT}/${OD_MODEL_DOWNLOAD_PATH}"

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
#          Discrete GPUs have their own VRAM (queried via sysfs).
#          A higher percentage is safe because VRAM isn't shared with
#          the OS, but we still reserve ~67% for model weights.
#   NPU  — Not applicable; OVMS ignores cache_size for NPU stateful
#          servables, so this function does not handle NPU.
#
# Users can override all of this by exporting OVMS_CACHE_SIZE_GB.
get_ovms_cache_size() {
    local target_device="$1"
    # Allow user override via OVMS_CACHE_SIZE_GB environment variable (validated at startup)
    if [[ -n "${OVMS_CACHE_SIZE_GB:-}" ]]; then
        echo -e "[ovms-service] ${YELLOW}OVMS_CACHE_SIZE_GB is set — overriding dynamic cache size with ${OVMS_CACHE_SIZE_GB} GB${NC}" >&2
        echo "$OVMS_CACHE_SIZE_GB"
        return
    fi

    local total_ram_gb
    total_ram_gb=$(awk '/MemTotal/ {printf "%d", $2/1024/1024}' /proc/meminfo)

    local cache_gb
    case "$target_device" in
        *GPU*)
            # Detect dedicated VRAM via sysfs (mem_info_vram_total, i915/xe drivers).
            local vram_bytes=0
            local vram_file
            for vram_file in \
                /sys/bus/pci/drivers/i915/*/mem_info_vram_total \
                /sys/bus/pci/drivers/xe/*/mem_info_vram_total; do
                [[ -f "$vram_file" ]] || continue
                local v
                v=$(cat "$vram_file" 2>/dev/null)
                if [[ -n "$v" && "$v" -gt "$vram_bytes" ]] 2>/dev/null; then
                    vram_bytes="$v"
                fi
            done

            # xe reports dedicated VRAM through the cgroup device-memory
            # controller on systems where mem_info_vram_total is unavailable.
            if [[ "$vram_bytes" -eq 0 && -r /sys/fs/cgroup/dmem.capacity ]]; then
                vram_bytes=$(awk '$1 ~ /\/vram/ && $2 > max { max = $2 } END { print max + 0 }' \
                    /sys/fs/cgroup/dmem.capacity)
            fi

            if [[ "$vram_bytes" -gt 0 ]] 2>/dev/null; then
                # dGPU: ~33% of dedicated VRAM, clamped to [2, 16]
                local dgpu_vram_gb=$((vram_bytes / 1073741824))
                cache_gb=$((dgpu_vram_gb * 33 / 100))
                cache_gb=$(( cache_gb < 2 ? 2 : cache_gb > 16 ? 16 : cache_gb ))
            else
                # VRAM not readable (iGPU/shared memory): fall back to 25% of system RAM, [2, 6] GB.
                echo -e "${YELLOW}WARNING: Could not read GPU VRAM from sysfs. Assuming iGPU or shared-memory GPU.${NC}" >&2
                echo -e "${YELLOW}         If this is a discrete GPU, set OVMS_CACHE_SIZE_GB to the correct value.${NC}" >&2
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
ovms_ms_model_dir() {
    local source_model="$1"
    local target_device="$2"
    local weight_format="$3"
    local device_lc format_lc
    device_lc=$(printf '%s' "$target_device" | tr '[:upper:]' '[:lower:]')
    format_lc=$(printf '%s' "$weight_format" | tr '[:upper:]' '[:lower:]')
    printf '%s/%s/openvino_models/%s/%s/%s' \
        "${OV_MODELS_ROOT}" "${OVMS_MS_DOWNLOAD_PATH}" "${device_lc}" "${format_lc}" "${source_model}"
}

# Export a model for OVMS via the model-download microservice (ephemeral).
# Storage-aware naming {model}_{device}_{format} lets multiple configs coexist.
export_model_for_ovms() {
    local source_model="$1"
    local target_device="$2"
    local weight_format="$3"
    local pipeline_type="$4"
    local storage_model_name cache_size model_type config_json model_dir
    local ms_args=()

    if [ -z "$source_model" ]; then
        echo -e "${RED}ERROR: Missing source model for OVMS export.${NC}" >&2
        return 1
    fi

    # Generate storage-aware model name that includes device and format
    storage_model_name=$(get_ovms_storage_model_name "$source_model" "$target_device" "$weight_format")

    cache_size=$(get_ovms_cache_size "$target_device") || return 1
    echo -e "[ovms-service] ${BLUE}Cache size: ${YELLOW}${cache_size} GB${NC} for device ${YELLOW}${target_device}${NC}"

    # A non-empty pipeline_type (e.g. VLM_CB) marks a vision-language model.
    if [ -n "$pipeline_type" ]; then
        model_type="vlm"
        config_json="{\"pipeline_type\":\"${pipeline_type}\"}"
    else
        model_type="llm"
        config_json=""
    fi

    mkdir -p "${OV_MODELS_ROOT}"

    ms_args=(
        --model-name "$source_model"
        --hub openvino
        --type "$model_type"
        --is-ovms
        --precision "$weight_format"
        --device "$target_device"
        --cache-size "$cache_size"
        --download-path "$OVMS_MS_DOWNLOAD_PATH"
    )
    [ -n "$config_json" ] && ms_args+=(--config-json "$config_json")

    # The microservice handles gated models via the HF_TOKEN env (forwarded by
    # download_model_via_ms); no host-side `hf auth login` is required.
    if ! download_model_via_ms "${OV_MODELS_ROOT}" "huggingface,openvino" "${ms_args[@]}"; then
        echo -e "${RED}ERROR: Failed to export the model '${source_model}' for OVMS via model-download.${NC}" >&2
        return 1
    fi

    fix_model_dir_ownership "${OV_MODELS_ROOT}/${OVMS_MS_DOWNLOAD_PATH}"

    model_dir=$(ovms_ms_model_dir "$source_model" "$target_device" "$weight_format")
    if [ ! -f "${model_dir}/graph.pbtxt" ]; then
        echo -e "${RED}ERROR: Converted OVMS model not found at ${model_dir} (missing graph.pbtxt).${NC}" >&2
        return 1
    fi

    # Patch the KV cache size in graph.pbtxt to the desired value.
    local existing_cache_size
    existing_cache_size=$(grep -oP 'cache_size:\s*\K[0-9]+' "${model_dir}/graph.pbtxt" 2>/dev/null)
    if [[ -n "$existing_cache_size" && "$existing_cache_size" -ne "$cache_size" ]]; then
        sed -i "s/cache_size:\s*${existing_cache_size}/cache_size: ${cache_size}/" "${model_dir}/graph.pbtxt"
        echo -e "[ovms-service] ${BLUE}Updated cache size: ${YELLOW}${existing_cache_size} → ${cache_size} GB${NC} in graph.pbtxt"
    fi

    # Register the converted model under its storage-aware name in OVMS config.
    add_model_to_ovms_config "${OV_MODELS_ROOT}/${OVMS_MS_DOWNLOAD_PATH}/config.json" "${storage_model_name}" "${model_dir}"
}

ensure_ovms_model() {
    local model_name="$1"
    local target_device="$2"
    local weight_format="$3"
    local pipeline_type="$4"
    local ovms_model_config="${OV_MODELS_ROOT}/${OVMS_MS_DOWNLOAD_PATH}/config.json"
    local storage_model_name
    local model_path

    # Generate storage-aware model name (includes device and format)
    storage_model_name=$(get_ovms_storage_model_name "$model_name" "$target_device" "$weight_format")
    model_path=$(ovms_ms_model_dir "$model_name" "$target_device" "$weight_format")

    # Check if model folder already exists with this device/format configuration
    if [ -d "$model_path" ] && [ -f "${model_path}/graph.pbtxt" ]; then
        echo -e "[ovms-service] ${GREEN}Model ${YELLOW}${storage_model_name}${GREEN} already exists. Skipping export.${NC}"

        # Compute the desired cache size and update graph.pbtxt if it differs
        local desired_cache_size existing_cache_size
        desired_cache_size=$(get_ovms_cache_size "$target_device") || return 1
        existing_cache_size=$(grep -oP 'cache_size:\s*\K[0-9]+' "${model_path}/graph.pbtxt" 2>/dev/null)

        if [[ -n "$existing_cache_size" && "$existing_cache_size" -ne "$desired_cache_size" ]]; then
            fix_model_dir_ownership "${model_path}"
            sed -i "s/cache_size:\s*${existing_cache_size}/cache_size: ${desired_cache_size}/" "${model_path}/graph.pbtxt" || {
                echo -e "${RED}ERROR: Failed to patch cache_size in ${model_path}/graph.pbtxt${NC}" >&2
                return 1
            }
            echo -e "[ovms-service] ${BLUE}Updated cache size: ${YELLOW}${existing_cache_size} → ${desired_cache_size} GB${NC} in graph.pbtxt"
        fi

        # Ensure it's registered in config.json (add_model_to_ovms_config is idempotent)
        add_model_to_ovms_config "${ovms_model_config}" "${storage_model_name}" "${model_path}"
    else
        echo -e "[ovms-service] ${YELLOW}Model ${RED}${storage_model_name}${YELLOW} not found. Exporting...${NC}"
        
        # Export the model
        export_model_for_ovms \
            "$model_name" \
            "$target_device" \
            "$weight_format" \
            "$pipeline_type" || return 1
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
            DEPLOYMENT_LABEL="Unified single UI for summarization and searching. For searching over text embeddings of summaries."
            UI_PROFILE="singleton_unified_ui"
            APP_COMPOSE_FILE="${APP_COMPOSE_FILE} -f docker/compose.summary.yaml -f docker/compose.search.yaml"
            ;;
        --dual)
            export VS_INDEX_NAME="video_frame_embeddings"
            export NGINX_UI_CONFIG="${nginx_config_dir}/dual_ui.conf"
            DEPLOYMENT_LABEL="Dual UI (Separate Summary and Search UI) deployment. For summarizing video content and searching over video frame embeddings."
            UI_PROFILE="dual_ui"
            APP_COMPOSE_FILE="${APP_COMPOSE_FILE} -f docker/compose.summary.yaml -f docker/compose.search.yaml"
            ;;
    esac

    APP_COMPOSE_FILE="${APP_COMPOSE_FILE} -f docker/compose.ui.yaml"
    mkdir -p ${VS_WATCHER_DIR}

    echo -e  "[pipeline-manager] ${GREEN}Setting up: ${DEPLOYMENT_LABEL}${NC}"
    if [ -n "${VS_INDEX_NAME}" ]; then
        echo -e  "[video-search] ${GREEN}Using vector-DB index: ${YELLOW}${VS_INDEX_NAME}${NC}"
    fi
    echo -e  "[nginx] ${GREEN}Using UI routing config: ${YELLOW}${NGINX_UI_CONFIG}${NC}"
    if [ "$ENABLE_VSS_COLLECTOR" = true ]; then
        APP_COMPOSE_FILE="$APP_COMPOSE_FILE -f docker/compose.telemetry.yaml"
        echo -e  "[telemetry] ${GREEN}vss-collector enabled (set ENABLE_VSS_COLLECTOR=true to keep enabled)${NC}"
    else
        echo -e  "[telemetry] ${YELLOW}vss-collector disabled (set ENABLE_VSS_COLLECTOR=true to enable)${NC}"
    fi

    # Validate expected OpenVINO artifact; directory-only checks can miss partial/incomplete model state.
    od_model_xml="${OD_MODEL_OUTPUT_DIR}/FP32/${OD_MODEL_NAME}.xml"
    od_model_bin="${OD_MODEL_OUTPUT_DIR}/FP32/${OD_MODEL_NAME}.bin"
    if [ "$1" != "--search" ] && [ "$2" != "config" ]; then
        if [ ! -f "${od_model_xml}" ] || [ ! -f "${od_model_bin}" ]; then
            echo -e  "[video-ingestion] ${YELLOW}Object detection model file not found at ${od_model_xml} or ${od_model_bin}. Running model conversion...${NC}"
            mkdir -p "${OD_MODEL_OUTPUT_DIR}"
            convert_object_detection_models
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
            export LLM_MODEL_NAME=${configured_ovms_llm_model:-${VLM_MODEL_NAME}}

            # VLM_TARGET_DEVICE and LLM_TARGET_DEVICE support: CPU, GPU, NPU, HETERO:...
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

            enforce_npu_int4_weight_format "VLM" "$VLM_TARGET_DEVICE" "VLM_COMPRESSION_WEIGHT_FORMAT"
            enforce_npu_int4_weight_format "LLM" "$LLM_TARGET_DEVICE" "LLM_COMPRESSION_WEIGHT_FORMAT"

            echo -e "[ovms-service] ${BLUE}Target devices — VLM: ${YELLOW}${VLM_TARGET_DEVICE}${BLUE} (${VLM_COMPRESSION_WEIGHT_FORMAT}), LLM: ${YELLOW}${LLM_TARGET_DEVICE}${BLUE} (${LLM_COMPRESSION_WEIGHT_FORMAT})${NC}"

            # Adjust concurrency and frame count for non-CPU devices
            if [[ "$VLM_TARGET_DEVICE" != "CPU" ]]; then
                export PM_VLM_CONCURRENT=1
                export PM_LLM_CONCURRENT=1
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
            
            echo -e "[ovms-service] ${GREEN}Storage models — VLM: ${YELLOW}${VLM_STORAGE_MODEL_NAME}${GREEN}, LLM: ${YELLOW}${LLM_STORAGE_MODEL_NAME}${NC}"

            if [ "$2" != "config" ]; then
                # Reset OVMS config to only include storage model names needed for this run
                if [ "$ovms_split_model" = true ]; then
                    reset_ovms_config "$VLM_STORAGE_MODEL_NAME" "$LLM_STORAGE_MODEL_NAME"
                else
                    reset_ovms_config "$VLM_STORAGE_MODEL_NAME"
                fi

                ensure_ovms_model \
                    "$VLM_MODEL_NAME" \
                    "$VLM_TARGET_DEVICE" \
                    "$VLM_COMPRESSION_WEIGHT_FORMAT" \
                    "VLM_CB" || return 1

                if [ "$ovms_split_model" = true ]; then
                    ensure_ovms_model \
                        "$LLM_MODEL_NAME" \
                        "$LLM_TARGET_DEVICE" \
                        "$LLM_COMPRESSION_WEIGHT_FORMAT" \
                        "" || return 1
                fi
            fi
        fi
    fi

    # if config is passed, set the command to only generate the config
    FINAL_ARG="up -d" && [ "$2" = "config" ] && FINAL_ARG="config"
    DOCKER_COMMAND="docker compose $APP_COMPOSE_FILE --profile $BACKEND_PROFILE --profile $UI_PROFILE $FINAL_ARG"
fi

# Run the Docker command to set up the application
if [ -n "$DOCKER_COMMAND" ]; then
    echo -e  "${GREEN}Running Docker command: $DOCKER_COMMAND ${NC}"
    eval "$DOCKER_COMMAND"
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
fi

# Reset all position arguments overrides
set --
