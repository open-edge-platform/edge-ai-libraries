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

# =================== Setup Mount Directories ======================
config_dir=${PWD}/config
nginx_config_dir=${config_dir}/nginx

export OVMS_CONFIG_DIR=${config_dir}/ovms_config
export OV_MODEL_DIR=${PWD}/ov_models
export RABBITMQ_CONFIG=${config_dir}/rmq.conf
export NGINX_BASE_CONFIG=${nginx_config_dir}/nginx.conf

# ================================= SETUP ALIASES ======================================
if [ "$#" -eq 1 ] && [ "$1" = "config" ]; then
    set -- "--dual" "config"
elif [ "$#" -eq 1 ] && [ "$1" = "--down" ]; then
    set -- "--stop"
elif [ "$#" -eq 2 ] && [ "$1" = "config" ]; then
    set -- "$2" "config"
elif [ "$#" -eq 0 ]; then
    set -- "--help"
fi
if [ "$1" = "--all" ]; then
    [ "$#" -eq 1 ] && set -- "--unified" || set -- "--unified" "$2"
fi

# =================== Function Definitions =========================
stop_containers() {
    echo -e "${YELLOW}Bringing down all the Docker containers... ${NC}"
    docker compose \
        -f docker/compose.base.yaml \
        -f docker/compose.summary.yaml \
        -f docker/compose.vllm.yaml \
        -f docker/compose.search.yaml \
        -f docker/compose.ui.yaml \
        -f docker/compose.telemetry.yaml \
        --profile ovms --profile vlm-ov --profile vllm \
        --profile dual_ui --profile singleton_unified_ui \
        --profile singleton_summary_ui \
        --profile singleton_search_ui \
        down
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to stop and remove containers.${NC}"
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
        return 1
    fi
    echo -e "${GREEN}All volumes were successfully removed. ${NC}"
    return 0
}

# =================== Argument Parsing and Handling =========================
if [ "$#" -gt 2 ]; then
    echo -e "${RED}ERROR: Too many arguments provided.${NC}"
    echo -e "${YELLOW}Use --help for usage information${NC}"
    return 1
fi

if [ "$#" -eq 1 ] && [ "$1" = "--help" ]; then
    echo -e "-----------------------------------------------------------------"
    echo -e  "${YELLOW}USAGE: ${GREEN}source setup.sh ${BLUE}[config ${GREEN}[--summary|--search|--dual|--unified|--all]${BLUE} | --summary | --search |"
    echo -e "       --dual | --unified | --all | --setenv | --down | --stop | --clean-data | --help]"
    echo -e  "${YELLOW}"
    echo -e  "         (no args), --help:  Shows this help message."
    echo -e  "                 --summary:  Deploy microservices with single summary UI."
    echo -e  "                  --search:  Deploy microservices with single search UI."
    echo -e  "                    --dual:  Deploy microservices with separate summary and search UIs."
    echo -e  "          --unified, --all:  Deploy microservices with one unified summary+search UI."
    echo -e  "                  --setenv:  Set environment variables without setting up application or starting any containers."
    echo -e  "            --down, --stop:  Bring down all the docker containers for the application."
    echo -e  "              --clean-data:  Bring down all the docker containers and remove all docker volumes for the user data."
    echo -e  "                    config:  Print the final compose configuration with all variables resolved without"
    echo -e  "                             starting containers. Mode defaults to --dual when omitted."
    echo -e  "                             Supported forms: config, config --summary|--search|--dual|--unified|--all"
    echo -e  "-----------------------------------------------------------------"
    return 0

fi

if [ "$#" -ge 1 ] \
     && [ "$1" != "--dual" ] && [ "$1" != "--unified" ] \
     && [ "$1" != "--summary" ] && [ "$1" != "--search" ] \
     && [ "$1" != "--stop" ] && [ "$1" != "--clean-data" ] \
     && [ "$1" != "--setenv" ] && [ "$1" != "config" ] \
     && [ "$1" != "--help" ]; then
    # Default case for unrecognized first option
    echo -e "${RED}Unknown option: $1 ${NC}"
    echo -e "${YELLOW}Use --help for usage information${NC}"
    set --
    return 1

elif [ "$#" -eq 2 ] && [ "$1" = "config" ] \
    && [ "$2" != "--summary" ] && [ "$2" != "--search" ] \
    && [ "$2" != "--dual" ] && [ "$2" != "--unified" ] && [ "$2" != "--all" ]; then
    echo -e "${RED}Invalid argument combination: '$1 $2'${NC}"
    echo -e "${YELLOW}Valid forms: config, config --summary, config --search, config --dual, config --unified, config --all${NC}"
    echo -e "${YELLOW}Use --help for usage information${NC}"
    return 1

elif [ "$#" -eq 2 ] && [ "$1" != "config" ] && [ "$2" != "config" ]; then
    echo -e "${RED}Invalid argument combination: '$1 $2'${NC}"
    echo -e "${YELLOW}Valid two-argument forms are '<mode> config' or 'config <mode>'${NC}"
    echo -e "${YELLOW}Use --help for usage information${NC}"
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

# env for vlm-openvino-serving
export VLM_HOST_PORT=9766
export VLM_MODEL_NAME=${VLM_MODEL_NAME}
export VLM_COMPRESSION_WEIGHT_FORMAT=int8
export VLM_DEVICE=CPU
export VLM_SEED=42
export WORKERS=${WORKERS:-6}
export VLM_LOG_LEVEL=${VLM_LOG_LEVEL:-info}
export VLM_MAX_COMPLETION_TOKENS=${VLM_MAX_COMPLETION_TOKENS}
export VLM_ACCESS_LOG_FILE=${VLM_ACCESS_LOG_FILE:-/dev/null}
export VLM_TELEMETRY_PATH=${VLM_TELEMETRY_PATH:-/opt/vlm_telemetry.jsonl}

if [ -z "$VLM_TELEMETRY_MAX_RECORDS" ]; then
    export VLM_TELEMETRY_MAX_RECORDS=100
elif ! [[ "$VLM_TELEMETRY_MAX_RECORDS" =~ ^[0-9]+$ ]] || [ "$VLM_TELEMETRY_MAX_RECORDS" -le 0 ]; then
    echo -e "[vlm-openvino-serving] ${YELLOW}Invalid VLM_TELEMETRY_MAX_RECORDS: ${VLM_TELEMETRY_MAX_RECORDS}. Using default 100.${NC}"
    export VLM_TELEMETRY_MAX_RECORDS=100
fi

export VLM_TELEMETRY_MAX_RECORDS=$VLM_TELEMETRY_MAX_RECORDS
export VLM_HOST=vlm-openvino-serving
export VLM_ENDPOINT=http://${VLM_HOST}:8000/v1
export ENABLE_VLLM=${ENABLE_VLLM:-false}
export VLLM_HOST=vllm-cpu-service
export VLLM_HOST_PORT=${VLLM_HOST_PORT:-8200}
export VLLM_ENDPOINT=http://${VLLM_HOST}:8000/v1
export USER_ID=$(id -u)
export USER_GROUP_ID=$(id -g)
export VIDEO_GROUP_ID=$(getent group video | awk -F: '{printf "%s\n", $3}')
export RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')

# Set VLM_OPENVINO_LOG_LEVEL based on VLM_LOG_LEVEL
# OpenVINO log levels: 0=NO, 1=ERR, 2=WARNING, 3=INFO, 4=DEBUG, 5=TRACE
case "${VLM_LOG_LEVEL}" in
    "debug")
        export VLM_OPENVINO_LOG_LEVEL=4  # DEBUG
        export VLM_ACCESS_LOG_FILE=${VLM_ACCESS_LOG_FILE:--}
        ;;
    "info")
        export VLM_OPENVINO_LOG_LEVEL=0  # INFO
        export VLM_ACCESS_LOG_FILE=${VLM_ACCESS_LOG_FILE:-/dev/null}
        ;;
    "warning")
        export VLM_OPENVINO_LOG_LEVEL=2  # WARNING
        export VLM_ACCESS_LOG_FILE=${VLM_ACCESS_LOG_FILE:--}
        ;;
    "error")
        export VLM_OPENVINO_LOG_LEVEL=1  # ERR
        export VLM_ACCESS_LOG_FILE=${VLM_ACCESS_LOG_FILE:--}
        ;;
    *)
        export VLM_OPENVINO_LOG_LEVEL=0  # INFO (default)
        export VLM_ACCESS_LOG_FILE=${VLM_ACCESS_LOG_FILE:-/dev/null}
        ;;
esac

# OpenVINO Configuration (optional)
# OV_CONFIG allows you to pass OpenVINO configuration parameters as a JSON string
# If not set, the default configuration will be: {"PERFORMANCE_HINT": "LATENCY"}
if [ -n "$OV_CONFIG" ]; then
    export OV_CONFIG=$OV_CONFIG
    echo -e "[vlm-openvino-serving] ${GREEN}Using custom OpenVINO configuration: ${YELLOW}$OV_CONFIG${NC}"
else
    unset OV_CONFIG
    # Default configuration will be handled by the VLM service
    echo -e "[vlm-openvino-serving] ${GREEN}Using default OpenVINO configuration: ${YELLOW}{\"PERFORMANCE_HINT\": \"LATENCY\"}${NC}"
fi

# env for pipeline-manager
export PM_HOST_PORT=3001
export PM_SUMMARIZATION_MAX_COMPLETION_TOKENS=4000
export PM_CAPTIONING_MAX_COMPLETION_TOKENS=1024
export PM_LLM_MAX_CONTEXT_LENGTH=${PM_LLM_MAX_CONTEXT_LENGTH:-90000}
export PM_LLM_CONCURRENT=2
export PM_VLM_CONCURRENT=4
PM_MULTI_FRAME_COUNT_DEFAULTED=false
if [[ -z "${PM_MULTI_FRAME_COUNT+x}" ]]; then
    export PM_MULTI_FRAME_COUNT=12
    PM_MULTI_FRAME_COUNT_DEFAULTED=true
fi
export PM_MINIO_BUCKET=video-summary

# env for ovms-service
export LLM_DEVICE=CPU
export LLM_MODEL_API="v1/models"
export OVMS_LLM_MODEL_NAME=${OVMS_LLM_MODEL_NAME}
export OVMS_HTTP_HOST_PORT=8300
export OVMS_GRPC_HOST_PORT=9300
export OVMS_HOST=ovms-service

# env for video-ingestion-service
export EVAM_HOST=video-ingestion
export EVAM_PIPELINE_HOST_PORT=8090
export EVAM_DEVICE=CPU

# env for rabbitmq
export RABBITMQ_AMQP_HOST_PORT=5672
export RABBITMQ_MANAGEMENT_UI_HOST_PORT=15672
export RABBITMQ_MQTT_HOST_PORT=1883
export RABBITMQ_USER=${RABBITMQ_USER}  # Set this in your shell before running the script
export RABBITMQ_PASSWORD=${RABBITMQ_PASSWORD} # Set this in your shell before running the script
export RABBITMQ_HOST=rabbitmq-service

# env for postgres
export POSTGRES_HOST_PORT=5432
export POSTGRES_USER=${POSTGRES_USER}  # Set this in your shell before running the script
export POSTGRES_PASSWORD=${POSTGRES_PASSWORD}  # Set this in your shell before running the script
export POSTGRES_DB=video_summary_db
export POSTGRES_HOST=postgres-service

# env for audio-analyzer service
export AUDIO_HOST_PORT=8999
export AUDIO_ENABLED_MODELS=${ENABLED_WHISPER_MODELS}
export AUDIO_MAX_FILE=314572800 # 300MB
export AUDIO_HOST=audio-analyzer
export AUDIO_ENDPOINT=http://$AUDIO_HOST:8000

# env for minio-service
export MINIO_API_HOST_PORT=4001
export MINIO_CONSOLE_HOST_PORT=4002
export MINIO_HOST=minio-service
export MINIO_ROOT_USER=${MINIO_ROOT_USER} # Set this in your shell before running the script
export MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD} # Set this in your shell before running the script

# env for vdms-vector-db
export VDMS_VDB_HOST_PORT=55555
export VDMS_VDB_HOST=vdms-vector-db

# env for vdms-dataprep-ms
export VDMS_DATAPREP_HOST_PORT=6016
export VDMS_DATAPREP_HOST=vdms-dataprep
export VDMS_DATAPREP_ENDPOINT=http://$VDMS_DATAPREP_HOST:8000
export VDMS_PIPELINE_MANAGER_UPLOAD=http://pipeline-manager:3000
export DEFAULT_BUCKET_NAME="vdms-bucket"

# YOLOX model volume configuration for object detection
export YOLOX_MODELS_VOLUME_NAME="vdms-yolox-models"
export YOLOX_MODELS_MOUNT_PATH="/app/models/yolox"

# Embedding processing mode settings (SDK vs API)
# EMBEDDING_PROCESSING_MODE options:
#   - "sdk": Use multimodal embedding service directly as SDK (optimized approach with better memory usage, default)
#   - "api": Use HTTP API calls to multimodal embedding service (existing approach)
export EMBEDDING_PROCESSING_MODE=${EMBEDDING_PROCESSING_MODE:-"sdk"}

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
export VDMS_DATAPREP_LOG_LEVEL=${VDMS_DATAPREP_LOG_LEVEL:-INFO}
export MAX_PARALLEL_WORKERS=${MAX_PARALLEL_WORKERS:-""}
export EMBEDDING_BATCH_SIZE=${EMBEDDING_BATCH_SIZE:-32}
export ALLOW_ORIGINS=${ALLOW_ORIGINS:-*}
export ALLOW_METHODS=${ALLOW_METHODS:-*}
export ALLOW_HEADERS=${ALLOW_HEADERS:-*}

# env for multimodal-embedding-serving (unified embedding service)
export EMBEDDING_SERVER_PORT=9777
# export EMBEDDING_MODEL_NAME=${EMBEDDING_MODEL_NAME}  # Must be explicitly provided - no default
export DEFAULT_START_OFFSET_SEC=0
export DEFAULT_CLIP_DURATION=${DEFAULT_CLIP_DURATION:--1}
export DEFAULT_NUM_FRAMES=64
export EMBEDDING_USE_OV=${EMBEDDING_USE_OV:-$SDK_USE_OPENVINO}
export OV_MODELS_DIR=${OV_MODELS_DIR:-"/app/ov_models"}
export EMBEDDING_OV_MODELS_DIR=${EMBEDDING_OV_MODELS_DIR:-$OV_MODELS_DIR}
# NOTE: The default OpenVINO performance mode has been changed from "LATENCY" to "THROUGHPUT".
# This impacts inference characteristics: "THROUGHPUT" optimizes for overall throughput, while "LATENCY" optimizes for response time.
# Please review user documentation or migration notes for details on this change.
export OV_PERFORMANCE_MODE=${OV_PERFORMANCE_MODE:-"THROUGHPUT"}
echo -e "[multimodal-embedding-serving] ${GREEN}OpenVINO performance mode: ${YELLOW}$OV_PERFORMANCE_MODE${NC}"

# Device Configuration
export VDMS_DATAPREP_DEVICE=${VDMS_DATAPREP_DEVICE:-"CPU"}
export SDK_USE_OPENVINO=${SDK_USE_OPENVINO:-true}

if [ "$ENABLE_EMBEDDING_GPU" = true ]; then
    export VDMS_DATAPREP_DEVICE=GPU
fi


# Device Configuration Helper Functions
configure_device() {
    local device=${1:-"CPU"}

    echo -e "${BLUE}Configuring device for all processing components: ${YELLOW}${device}${NC}"
    echo -e "${BLUE}   This affects: embedding model, and object detection${NC}"

    if [[ "${device}" == GPU* ]]; then
        echo -e "${YELLOW}⚙️  Setting up GPU configuration...${NC}"
        
        # Check if Intel GPU is available
        if ! lspci | grep -i "vga.*intel" > /dev/null 2>&1; then
            echo -e "${RED}Warning: No Intel GPU detected. GPU mode may not work properly.${NC}"
        else
            echo -e "${GREEN}Intel GPU detected${NC}"
        fi
        
        # Check if /dev/dri exists for GPU access
        if [[ ! -d "/dev/dri" ]]; then
            echo -e "${RED}Warning: /dev/dri not found. GPU acceleration may not be available.${NC}"
        else
            echo -e "${GREEN}DRI devices found for GPU acceleration${NC}"
        fi
        
        # Set GPU-specific configuration
        export VDMS_DATAPREP_DEVICE="${device}"
        export SDK_USE_OPENVINO=true  # Force OpenVINO for GPU mode
        
        echo -e "${GREEN}GPU mode configured for all components:${NC}"
        echo -e "   • OpenVINO: ${YELLOW}enabled${NC} (required for GPU)"
        echo -e "   • Processing Device: ${YELLOW}GPU${NC} (decord, embedding, detection)"
        echo -e "   • Video decoding: ${YELLOW}GPU-accelerated${NC}"
        
    else
        echo -e "${BLUE} CPU mode configured for all components${NC}"
        export VDMS_DATAPREP_DEVICE="${device}"
    fi
}

# Device mode selection
if [[ "${VDMS_DATAPREP_DEVICE}" == GPU* ]]; then
    configure_device "${VDMS_DATAPREP_DEVICE}"
else
    configure_device "CPU"
fi

export EMBEDDING_DEVICE=${EMBEDDING_DEVICE:-$VDMS_DATAPREP_DEVICE}

export MULTIMODAL_EMBEDDING_HOST=multimodal-embedding-serving
export MULTIMODAL_EMBEDDING_ENDPOINT=http://$MULTIMODAL_EMBEDDING_HOST:8000/embeddings

processing_scope="vdms-dataprep video decoding, YOLOX detection, and embedding execution"
if [[ "${EMBEDDING_PROCESSING_MODE}" == "api" ]]; then
    processing_scope+=", plus the multimodal-embedding-serving container"
fi

if [ $1 != "--summary" ]; then
    if [ "$1" = "--unified" ]; then
        embedding_model_display="${TEXT_EMBEDDING_MODEL:-"(not provided)"}"
    else
        embedding_model_display="${MULTIMODAL_EMBEDDING_MODEL:-"(not provided)"}"
    fi

    embedding_endpoint_display=${MULTIMODAL_EMBEDDING_ENDPOINT:-"(not configured)"}

    if [[ "${EMBEDDING_PROCESSING_MODE}" == "sdk" ]]; then
        embedding_mode_details="SDK mode keeps embeddings in-process within vdms-dataprep; no external HTTP calls are made."
    else
        embedding_mode_details="API mode routes embeddings to multimodal-embedding-serving at ${embedding_endpoint_display}."
    fi

    echo -e "[vdms-dataprep] ${BLUE}Runtime Summary:${NC}"
    echo -e "   • [vdms-dataprep] Processing Device: ${YELLOW}${VDMS_DATAPREP_DEVICE}${NC} (${processing_scope})."
    if [[ "${EMBEDDING_PROCESSING_MODE}" == "api" ]]; then
        echo -e "   • [multimodal-embedding-serving] Embedding Service Device: ${YELLOW}${EMBEDDING_DEVICE}${NC} (HTTP mode container)."
    fi
    echo -e "   • [vdms-dataprep] Embedding Mode: ${YELLOW}${EMBEDDING_PROCESSING_MODE}${NC} — ${embedding_mode_details}"
    echo -e "   • [multimodal-embedding-serving] Embedding Model: ${YELLOW}${embedding_model_display}${NC}"
fi

# Frame-to-Video Aggregation Settings for search-ms
export AGGREGATION_ENABLED=${AGGREGATION_ENABLED:-true}
export AGGREGATION_SEGMENT_DURATION=${AGGREGATION_SEGMENT_DURATION:-8}
export AGGREGATION_MIN_GAP=${AGGREGATION_MIN_GAP:-0}
export AGGREGATION_MAX_RESULTS=${AGGREGATION_MAX_RESULTS:-20}
export AGGREGATION_INITIAL_K=${AGGREGATION_INITIAL_K:-1000}
export AGGREGATION_CONTEXT_SEEK_OFFSET_SECONDS=${AGGREGATION_CONTEXT_SEEK_OFFSET_SECONDS:-0}

# env for video-search
export VS_HOST_PORT=7890
export VS_WATCHER_DIR=${VS_WATCHER_DIR:-$PWD/data}
export VS_DELETE_PROCESSED_FILES=${VS_DELETE_PROCESSED_FILES:-false}
export VS_INITIAL_DUMP=${VS_INITIAL_DUMP:-false}
export VS_WATCH_DIRECTORY_RECURSIVE=${VS_WATCH_DIRECTORY_RECURSIVE:-false}
export VS_DEBOUNCE_TIME=${VS_DEBOUNCE_TIME:-10}
export VS_HOST=video-search
export VS_ENDPOINT=http://$VS_HOST:8000

# If nginx not being used, set this in your shell with pipeline manager's complete url with host and port. 
export UI_PM_ENDPOINT=${UI_PM_ENDPOINT:-/manager}
# if nginx not being used, set this in your shell with minio's complete url with host and port.
export UI_ASSETS_ENDPOINT=${UI_ASSETS_ENDPOINT:-/datastore}

export CONFIG_SOCKET_APPEND=${CONFIG_SOCKET_APPEND} # Set this to CONFIG_ON in your shell, if nginx not being used

# Telemetry collector toggle for search (disabled by default)
export ENABLE_VSS_COLLECTOR=${ENABLE_VSS_COLLECTOR:-false}

# Object detection model settings
export OD_MODEL_NAME=${OD_MODEL_NAME}
export OD_MODEL_TYPE=${OD_MODEL_TYPE:-"yolo_v8"}
export OD_MODEL_OUTPUT_DIR=${OV_MODEL_DIR}/yoloworld/v2
echo -e "[video-ingestion] ${GREEN}Using object detection model: ${YELLOW}$OD_MODEL_NAME of type $OD_MODEL_TYPE ${NC}"
echo -e "[video-ingestion] ${GREEN}Output directory for object detection model: ${YELLOW}$OD_MODEL_OUTPUT_DIR ${NC}"


# Verify if required environment variables are set in current shell, only when container down or clean is not requested.
if [ "$1" != "--down" ] && [ "$1" != "--stop" ] && [ "$1" != "--clean-data" ] && [ "$2" != "config" ]; then
    if [ -z "$MINIO_ROOT_USER" ]; then
        echo -e "${RED}ERROR: MINIO_ROOT_USER is not set in your shell environment.${NC}"
        return 1
    fi
    if [ -z "$MINIO_ROOT_PASSWORD" ]; then
        echo -e "${RED}ERROR: MINIO_ROOT_PASSWORD is not set in your shell environment.${NC}"
        return 1
    fi
    if [ -z "$POSTGRES_USER" ]; then
        echo -e "${RED}ERROR: POSTGRES_USER is not set in your shell environment.${NC}"
        return 1
    fi
    if [ -z "$POSTGRES_PASSWORD" ]; then
        echo -e "${RED}ERROR: POSTGRES_PASSWORD is not set in your shell environment.${NC}"
        return 1
    fi
    if [ -z "$RABBITMQ_USER" ]; then
        echo -e "${RED}ERROR: RABBITMQ_USER is not set in your shell environment.${NC}"
        return 1
    fi
    if [ -z "$RABBITMQ_PASSWORD" ]; then
        echo -e "${RED}ERROR: RABBITMQ_PASSWORD is not set in your shell environment.${NC}"
        return 1
    fi
    if [ "$1" != "--search" ]; then
        if [ -z "$VLM_MODEL_NAME" ]; then
            echo -e "${RED}ERROR: VLM_MODEL_NAME is not set in your shell environment.${NC}"
            echo -e "${YELLOW}This is required for all modes except --search.${NC}"
            return 1
        fi
        if [ -z "$ENABLED_WHISPER_MODELS" ]; then
            echo -e "${RED}ERROR: ENABLED_WHISPER_MODELS is not set in your shell environment.${NC}"
            echo -e "${YELLOW}This is required for all modes except --search.${NC}"
            return 1
        fi
        if [ -z "$OD_MODEL_NAME" ]; then
            echo -e "${RED}ERROR: OD_MODEL_NAME is not set in your shell environment.${NC}"
            echo -e "${YELLOW}This is required for all modes except --search.${NC}"
            return 1
        fi
        if [ "$ENABLE_OVMS_LLM_SUMMARY" = true ] || [ "$ENABLE_OVMS_LLM_SUMMARY_GPU" = true ]; then
            if [ -z "$OVMS_LLM_MODEL_NAME" ]; then
                echo -e "${RED}ERROR: OVMS_LLM_MODEL_NAME is not set in your shell environment.${NC}"
                echo -e "${YELLOW}This is required for all modes except --search.${NC}"
                return 1
            fi
        fi
    fi
    if { [ "$1" = "--search" ] || [ "$1" = "--dual" ]; } && [ -z "$MULTIMODAL_EMBEDDING_MODEL" ]; then
        echo -e "${RED}ERROR: MULTIMODAL_EMBEDDING_MODEL is not set in your shell environment.${NC}"
        echo -e "${YELLOW}This is required for both SDK and API embedding modes for Video Search.${NC}"
        return 1
    fi
    
    # Validate embedding processing mode
    if [[ "$EMBEDDING_PROCESSING_MODE" != "api" && "$EMBEDDING_PROCESSING_MODE" != "sdk" ]]; then
        echo -e "${RED}Invalid EMBEDDING_PROCESSING_MODE: $EMBEDDING_PROCESSING_MODE${NC}"
        echo -e "${YELLOW}Valid options are: 'api' or 'sdk'${NC}"
        return 1
    fi

    # Enforce dedicated text-embedding selection only for unified mode.
    if [ "$1" = "--unified" ] && [ -z "$TEXT_EMBEDDING_MODEL" ]; then
        echo -e "${RED}ERROR: TEXT_EMBEDDING_MODEL is not set in your shell environment.${NC}"
        echo -e "${YELLOW}This is required for --unified/--all mode.${NC}"
        return 1
    fi
    
fi

# if only base environment variables are to be set without deploying application, exit here
if [ "$1" = "--setenv" ]; then
    echo -e  "${BLUE}Done setting up all environment variables. ${NC}"
    return 0
fi

# Add rendering device group ID for GPU support when needed
# Check if render device exist
if ls /dev/dri/render* >/dev/null 2>&1; then
    echo -e  "${GREEN}RENDER device exist. Getting the GID...${NC}"
    export RENDER_DEVICE_GID=$(stat -c "%g" /dev/dri/render* | head -n 1)
else
    echo -e  "${YELLOW}RENDER device does not exist. Setting RENDER_DEVICE_GID to 0 ${NC}"
    export RENDER_DEVICE_GID=0
fi

# Set DRI_MOUNT_PATH based on whether /dev/dri exists and is not empty
if [ -d /dev/dri ] && [ "$(ls -A /dev/dri)" ]; then
    export DRI_MOUNT_PATH="/dev/dri"
    echo -e "${GREEN}/dev/dri found and not empty. Will mount.${NC}"
else
    export DRI_MOUNT_PATH="/dev/null"
    echo -e "${YELLOW}/dev/dri not found or empty, will mount /dev/null instead.${NC}"
fi

# Function to convert object detection models
convert_object_detection_models() {
    echo -e  "Setting up Python environment for object detection model conversion..."
    # Check if python3-venv is already installed
    if ! dpkg-query -W -f='${Status}' python3-venv 2>/dev/null | grep -q "ok installed"; then
        echo -e  "Installing python3-venv package..."
        sudo apt install -y python3-venv
    else
        echo -e  "python3-venv is already installed, skipping installation"
    fi

    # Create and activate virtual environment for model conversion
    python3 -m venv ov_model_venv
    source ov_model_venv/bin/activate

    echo -e  "Installing required packages for model conversion..."
    pip install -q "ultralytics==8.3.232" "openvino==2025.4.1" --extra-index-url https://download.pytorch.org/whl/cpu
    
    # Run script to convert the model to OpenVINO format and verify conversion
    echo -e  "Converting object detection model: ${OD_MODEL_NAME} (${OD_MODEL_TYPE})..."
    python3 video-ingestion/resources/scripts/converter.py --model-name "${OD_MODEL_NAME}" --model-type "${OD_MODEL_TYPE}" --output-dir "${OD_MODEL_OUTPUT_DIR}"
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Model conversion failed for ${OD_MODEL_NAME}.${NC}"
    else
        echo -e "${GREEN}Model conversion succeeded for ${OD_MODEL_NAME}.${NC}"
        echo -e  "${BLUE}Object detection model ${OD_MODEL_NAME} has been successfully converted and saved to ${OD_MODEL_OUTPUT_DIR}${NC}"
    fi
    echo -e "Cleaning up virtual environment..."
    deactivate
    rm -rf ov_model_venv
}

# Function to export and save requested model for OVMS
export_model_for_ovms() {
    # Create a directory for model, model_export.py script and virtual environment
    curr_dir=$(pwd)
    mkdir -p ${config_dir}/ovms_config
    cd ${config_dir}/ovms_config

    # Download the OVMS model export script
    if [ ! -f export_model.py ]; then
        curl https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/tags/v2025.4.1/demos/common/export_models/export_model.py -o export_model.py
    else
        echo -e  "${YELLOW}Model export script already exists, skipping download${NC}"
    fi
    
    # Create a virtual environment for model export and activate it
    echo -e  "Creating Python virtual environment for model export..."
    # Check if python3-venv is already installed
    if ! dpkg-query -W -f='${Status}' python3-venv 2>/dev/null | grep -q "ok installed"; then
        echo -e  "Installing python3-venv package..."
        sudo apt install -y python3-venv
    else
        echo -e  "python3-venv is already installed, skipping installation"
    fi
    python3 -m venv ovms_venv
    source ovms_venv/bin/activate
    
    # Install requirements in the virtual environment
    local ovms_requirements_url="https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/tags/v2025.4.1/demos/common/export_models/requirements.txt"
    local tmp_requirements
    tmp_requirements=$(mktemp)

    if ! curl -fsSL "$ovms_requirements_url" -o "$tmp_requirements"; then
        echo -e "${RED}ERROR: Failed to download OVMS requirements from ${ovms_requirements_url}.${NC}"
        deactivate
        rm -rf ovms_venv
        rm -f "$tmp_requirements"
        return 1
    fi

    if grep -q '^transformers' "$tmp_requirements"; then
        sed -i 's/^transformers.*/transformers==4.53.3/' "$tmp_requirements"
    else
        echo 'transformers==4.53.3' >> "$tmp_requirements"
    fi

    pip install --no-cache-dir -r "$tmp_requirements"
    local pip_status=$?
    rm -f "$tmp_requirements"
    if [ $pip_status -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to install OVMS requirements.${NC}"
        deactivate
        rm -rf ovms_venv
        return 1
    fi
    if [ "$GATED_MODEL" = true ]; then
        pip install --no-cache-dir -U huggingface_hub[hf_xet]==0.36.0 # Install huggingface-hub for downloading gated models
        echo -e "${BLUE}Logging in to Hugging Face to access gated models...${NC}"
	hf auth login --token $HUGGINGFACE_TOKEN # Login to Hugging Face using the provided token
    fi
    mkdir -p models

    python3 export_model.py text_generation \
        --source_model $OVMS_LLM_MODEL_NAME \
        --weight-format $LLM_COMPRESSION_WEIGHT_FORMAT \
        --config_file_path models/config.json \
        --model_repository_path models \
        --target_device ${LLM_DEVICE} \
        --cache $OVMS_CACHE_SIZE \
        --overwrite_models
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to export the model for OVMS.${NC}"
        deactivate
        rm -rf ovms_venv
        return 1
    fi

    # Create a file to mark what device the model was generated for
    echo "${LLM_DEVICE}" > models/${OVMS_LLM_MODEL_NAME}/device_type.txt
    
    # Deactivate and remove the virtual environment
    echo -e  "Cleaning up virtual environment..."
    deactivate
    cd $curr_dir
}

if [ "$1" = "--summary" ] || [ "$1" = "--search" ] || [ "$1" = "--dual" ] || [ "$1" = "--unified" ]; then
    BACKEND_PROFILE="vlm-ov"
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
    if [ "$2" != "config" ]; then
        if [ ! -f "${od_model_xml}" ] || [ ! -f "${od_model_bin}" ]; then
            echo -e  "[vdms-dataprep] ${YELLOW}Object detection model file not found at ${od_model_xml} or ${od_model_bin}. Running model conversion...${NC}"
            mkdir -p "${OD_MODEL_OUTPUT_DIR}"
            convert_object_detection_models
        else
            echo -e  "[vdms-dataprep] ${YELLOW}Object detection model file found at ${od_model_xml}. Skipping model setup...${NC}"
        fi
    fi

    if [ "$ENABLE_VLLM" = true ]; then
        echo -e "[vllm-cpu-service] ${BLUE}Using vLLM for both chunk captioning and final summary${NC}"
        echo -e "[vllm-cpu-service] ${YELLOW}Disabling OVMS and vlm-openvino-serving because ENABLE_VLLM=true${NC}"
        BACKEND_PROFILE="vllm"
        export ENABLE_OVMS_LLM_SUMMARY=false
        export ENABLE_OVMS_LLM_SUMMARY_GPU=false
        export ENABLE_VLM_GPU=false
        export USE_OVMS_CONFIG=CONFIG_OFF
        export LLM_SUMMARIZATION_API=${VLLM_ENDPOINT}
        export VLM_ENDPOINT=${VLLM_ENDPOINT}
        export VLM_HOST=${VLLM_HOST}
        APP_COMPOSE_FILE="$APP_COMPOSE_FILE -f docker/compose.vllm.yaml"
    fi

    # Check if both LLM and VLM are configured for GPU. In which case, prioritize VLM for GPU and set OVMS to CPU
    if [ "$ENABLE_VLLM" != true ] && [ "$ENABLE_OVMS_LLM_SUMMARY_GPU" = true ] && \
       [ "$ENABLE_VLM_GPU" = true ]; then
        echo -e "[ovms-service] ${BLUE}Both VLM and LLM are configured for GPU. Resetting OVMS to run on CPU${NC}"
        export ENABLE_OVMS_LLM_SUMMARY_GPU="false"
    fi

    # If OVMS is to be used for summarization, set up the environment variables and compose files accordingly
    if [ "$ENABLE_VLLM" != true ] && { [ "$ENABLE_OVMS_LLM_SUMMARY" = true ] || [ "$ENABLE_OVMS_LLM_SUMMARY_GPU" = true ]; }; then
        echo -e "[ovms-service] ${BLUE}Using OVMS for generating final summary for the video${NC}"
        export USE_OVMS_CONFIG=CONFIG_ON
        export LLM_SUMMARIZATION_API=http://$OVMS_HOST/v3
        export LLM_MODEL_API="v1/config"

        # Set relevant variables, compose files and profiles based on whether GPU is used or not
        if [ "$ENABLE_OVMS_LLM_SUMMARY_GPU" = true ]; then
            echo -e "[ovms-service] ${BLUE}Using GPU acceleration for OVMS${NC}"
            export OVMS_CACHE_SIZE=2
            export LLM_COMPRESSION_WEIGHT_FORMAT=int4
            export LLM_DEVICE=GPU
            APP_COMPOSE_FILE="$APP_COMPOSE_FILE -f docker/compose.gpu_ovms.yaml --profile ovms"
        else
            echo -e "[ovms-service] ${BLUE}Running OVMS on CPU${NC}"
            export OVMS_CACHE_SIZE=10
            export LLM_COMPRESSION_WEIGHT_FORMAT=int8
            export LLM_DEVICE=CPU
            APP_COMPOSE_FILE="$APP_COMPOSE_FILE --profile ovms"
        fi

        # Setup OVMS model 
        ovms_model_config="${OVMS_CONFIG_DIR}/models/config.json"
        device_marker_file="${OVMS_CONFIG_DIR}/models/${OVMS_LLM_MODEL_NAME}/device_type.txt"    
        needs_export=false
        
        # Export model only if docker-compose config is not requested
        if [ "$2" != "config" ]; then

            # Check if model config exists            
            if [ ! -f "${ovms_model_config}" ]; then
                echo -e "[ovms-service] ${YELLOW}No existing model configurations found. Exporting model ${RED}${OVMS_LLM_MODEL_NAME}${YELLOW}...${NC}"
                needs_export=true
            # Check whether the model exists in OVMS config
            elif grep -q ${OVMS_LLM_MODEL_NAME} "${ovms_model_config}"; then
                echo -e "[ovms-service] ${YELLOW}Model ${RED}${OVMS_LLM_MODEL_NAME}${YELLOW} exists in OVMS config. Checking device type...${NC}"
                # If model exists, check if device type matches
                if [ -f "${device_marker_file}" ]; then
                    saved_device=$(cat "${device_marker_file}")
                    if [ "${saved_device}" != "${LLM_DEVICE}" ]; then
                        echo -e "[ovms-service] ${YELLOW}Model was exported for ${RED}${saved_device}${YELLOW}. Re-exporting model for ${RED}${LLM_DEVICE}${YELLOW}...${NC}"
                        needs_export=true
                    else
                        echo -e "[ovms-service] ${YELLOW}Model was exported for ${RED}${LLM_DEVICE}${YELLOW}. Skipping model setup...${NC}"
                    fi
                else
                    echo -e "[ovms-service] ${YELLOW}Device type information missing. Re-exporting model...${NC}"
                    needs_export=true
                fi
            else
                echo -e "[ovms-service] ${YELLOW}Model ${RED}${OVMS_LLM_MODEL_NAME}${YELLOW} not found in OVMS config. Exporting model...${NC}"
                needs_export=true
            fi
            
            # Export model if needed
            if [ "$needs_export" = true ]; then
                export_model_for_ovms
            fi
        fi
    elif [ "$ENABLE_VLLM" != true ]; then
        echo -e "[vlm-openvino-serving] ${BLUE}Using VLM for generating final summary for the video${NC}"
        export USE_OVMS_CONFIG=CONFIG_OFF
        export LLM_SUMMARIZATION_API=http://$VLM_HOST:8000/v1
    fi

    if [ "$ENABLE_VLLM" != true ]; then
        if [ "$ENABLE_VLM_GPU" = true ]; then
            export VLM_DEVICE=GPU
            export PM_VLM_CONCURRENT=1
            export PM_LLM_CONCURRENT=1
            export VLM_COMPRESSION_WEIGHT_FORMAT=int4
            if [ "$PM_MULTI_FRAME_COUNT_DEFAULTED" = true ]; then
                export PM_MULTI_FRAME_COUNT=6
            fi
            export WORKERS=1
            echo -e "[vlm-openvino-serving] ${BLUE}Using VLM for summarization on GPU${NC}"
        else
            export VLM_DEVICE=CPU
            echo -e "[vlm-openvino-serving] ${BLUE}Using VLM for summarization on CPU${NC}"
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
    echo -e "\n${RED}Failed: Some error occured while setting up one or more containers.${NC}"
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
