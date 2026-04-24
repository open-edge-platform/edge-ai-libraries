#!/bin/bash

# Color codes for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Setting variables for directories used as volume mounts. Could be required during stopping containers as well.
export OVMS_CONFIG_DIR=${PWD}/config/ovms_config
export OV_MODEL_DIR=${PWD}/ov_models
export CONFIG_DIR=${PWD}/config
export NGINX_CONFIG=${CONFIG_DIR}/nginx.conf
export RABBITMQ_CONFIG=${CONFIG_DIR}/rmq.conf

# Function to stop Docker containers
stop_containers() {
    echo -e "${YELLOW}Bringing down the Docker containers... ${NC}"
    docker compose -f docker/compose.base.yaml -f docker/compose.summary.yaml -f docker/compose.vllm.yaml -f docker/compose.search.yaml -f docker/compose.telemetry.yaml --profile ovms --profile vllm down
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to stop and remove containers.${NC}"
        return 1
    fi
    echo -e "${GREEN}All containers were successfully stopped and removed. ${NC}"
    return 0
}

# Setting command usage and invalid arguments handling before the actual setup starts
if [ "$#" -eq 0 ] ||  ([ "$#" -eq 1 ] && [ "$1" = "--help" ]); then
    # If no valid argument is passed, print usage information
    echo -e "-----------------------------------------------------------------"
    echo -e  "${YELLOW}USAGE: ${GREEN}source setup.sh ${BLUE}[--setenv | --down | --clean-data | --help | --summary ${GREEN}[config]${BLUE} | --search ${GREEN}[config]${BLUE} | --all ${GREEN}[config]${BLUE}]"
    echo -e  "${YELLOW}"
    echo -e  "  --setenv:     Set environment variables without starting any containers"
    echo -e  "  --summary:    Configure and bring up Video Summarization application"
    echo -e  "  --search:     Configure and bring up Video Search application"
    echo -e  "  --all:        Configure and bring up both Video Summarization and Video Search applications"
    echo -e  "  --down:       Bring down all the docker containers for the application which was brought up."
    echo -e  "  --clean-data: Bring down all the docker containers and remove all docker volumes for the user data."
    echo -e  "  --help:       Show this help message"
    echo -e  "  config:       Optional argument (only works with --summary, --search, or --all) to print the final"
    echo -e  "                compose configuration with all variables resolved without starting containers${NC}"
    echo -e "-----------------------------------------------------------------"
    return 0

elif [ "$#" -gt 2 ]; then
    echo -e "${RED}ERROR: Too many arguments provided.${NC}"
    echo -e "${YELLOW}Use --help for usage information${NC}"
    return 1

elif [ "$1" != "--help" ] && [ "$1" != "--summary" ] && [ "$1" != "--all" ] && [ "$1" != "--search" ] && [ "$1" != "--setenv" ] && [ "$1" != "--down" ] && [ "$1" != "--clean-data" ]; then
    # Default case for unrecognized first option
    echo -e "${RED}Unknown option: $1 ${NC}"
    echo -e "${YELLOW}Use --help for usage information${NC}"
    return 1

elif [ "$#" -eq 2 ] && [ "$2" != "config" ]; then
    # Invalid second argument
    echo -e "${RED}Unknown second argument: $2${NC}"
    echo -e "${YELLOW}The only valid second argument is 'config'${NC}"
    return 1
    
elif [ "$#" -eq 2 ] && [ "$2" = "config" ] && [ "$1" != "--summary" ] && [ "$1" != "--search" ] && [ "$1" != "--all" ]; then
    # Config argument used with incorrect first argument
    echo -e "${RED}The 'config' argument can only be used with --summary, --search, or --all${NC}"
    echo -e "${YELLOW}Use --help for usage information${NC}"
    return 1

elif [ "$1" = "--down" ]; then
    # If --down is passed, bring down the Docker containers
    echo -e "${YELLOW}Bringing down the Docker containers... ${NC}"
    stop_containers
    return $?

elif [ "$1" = "--clean-data" ]; then
    # If --clean-data is passed, bring down the Docker containers and remove volumes
    stop_containers
    if [ $? -ne 0 ]; then
        echo -e "${RED}ERROR: Failed to stop and remove containers.${NC}"
        return 1
    fi    

    echo -e "${GREEN}All containers were successfully stopped and removed. ${NC}"
    echo -e "${YELLOW}Removing Docker volumes created by the application... ${NC}"

    # Remove volumes 
    docker volume rm docker_minio_data docker_pg_data docker_vdms-db docker_audio_analyzer_data docker_data-prep docker_collector_signals 2>/dev/null || true
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}All volumes were successfully removed. ${NC}"
    else
        echo -e "${YELLOW}Note: Some volumes may not have existed or were already removed. ${NC}"
    fi
    echo -e "${GREEN}Clean operation completed successfully! ${NC}"
    return 0
fi

# Host port for nginx proxy server (port on which we access the application)
export APP_HOST_PORT=12345

# Export all environment variables
# Base configuration
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
export VLM_COMPRESSION_WEIGHT_FORMAT=${VLM_COMPRESSION_WEIGHT_FORMAT:-int8}
export VLM_TARGET_DEVICE=${VLM_TARGET_DEVICE:-CPU}
export USE_VLLM=${USE_VLLM:-CONFIG_OFF}
export ENABLE_VLLM=${ENABLE_VLLM:-false}
export VLLM_HOST=vllm-cpu-service
export VLLM_HOST_PORT=${VLLM_HOST_PORT:-8200}
export VLLM_ENDPOINT=http://${VLLM_HOST}:8000/v1
export USER_ID=$(id -u)
export USER_GROUP_ID=$(id -g)
export VIDEO_GROUP_ID=$(getent group video | awk -F: '{printf "%s\n", $3}')
export RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')

# env for pipeline-manager
export PM_HOST_PORT=3001
export PM_HOST=pipeline-manager
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
export PM_MINIO_BUCKET=video-summary

# env for ovms-service
export LLM_TARGET_DEVICE=${LLM_TARGET_DEVICE:-CPU}
export LLM_MODEL_NAME=${LLM_MODEL_NAME:-${OVMS_LLM_MODEL_NAME}}
export LLM_COMPRESSION_WEIGHT_FORMAT=${LLM_COMPRESSION_WEIGHT_FORMAT:-int8}
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
export OVMS_ALLOWED_MEDIA_DOMAINS=${OVMS_ALLOWED_MEDIA_DOMAINS:-${MINIO_HOST},localhost}

# env for vdms-vector-db
export VDMS_VDB_HOST_PORT=55555
export VDMS_VDB_HOST=vdms-vector-db

# env for vdms-dataprep-ms
export VDMS_DATAPREP_HOST_PORT=6016
export VDMS_DATAPREP_HOST=vdms-dataprep
export VDMS_DATAPREP_ENDPOINT=http://$VDMS_DATAPREP_HOST:8000
export VDMS_PIPELINE_MANAGER_UPLOAD=http://$PM_HOST:3000
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
export EMBEDDING_MODEL_NAME=${EMBEDDING_MODEL_NAME}  # Must be explicitly provided - no default
export TEXT_EMBEDDING_MODEL_NAME=${TEXT_EMBEDDING_MODEL_NAME}  # Optional - only required for unified case (--all)
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

embedding_model_display=${EMBEDDING_MODEL_NAME:-"(not provided)"}
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

# env for vss-ui
export UI_HOST_PORT=9998
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
if [ "$1" != "--down" ] && [ "$1" != "--clean-data" ] && [ "$2" != "config" ]; then
    if [ -z "$MINIO_ROOT_USER" ]; then
        echo -e "${RED}ERROR: MINIO_ROOT_USER is not set in your shell environment.${NC}"
        return
    fi

    if [ -z "$MINIO_ROOT_PASSWORD" ]; then
        echo -e "${RED}ERROR: MINIO_ROOT_PASSWORD is not set in your shell environment.${NC}"
        return
    fi

    if [ -z "$POSTGRES_USER" ]; then
        echo -e "${RED}ERROR: POSTGRES_USER is not set in your shell environment.${NC}"
        return
    fi
    if [ -z "$POSTGRES_PASSWORD" ]; then
        echo -e "${RED}ERROR: POSTGRES_PASSWORD is not set in your shell environment.${NC}"
        return
    fi
    if [ "$1" != "--search" ]; then
        if [ -z "$RABBITMQ_USER" ]; then
            echo -e "${RED}ERROR: RABBITMQ_USER is not set in your shell environment.${NC}"
            return
        fi
        if [ -z "$RABBITMQ_PASSWORD" ]; then
            echo -e "${RED}ERROR: RABBITMQ_PASSWORD is not set in your shell environment.${NC}"
            return
        fi
        if [ -z "$VLM_MODEL_NAME" ]; then
            echo -e "${RED}ERROR: VLM_MODEL_NAME is not set in your shell environment.${NC}"
            return
        fi
        if [ -z "$ENABLED_WHISPER_MODELS" ]; then
            echo -e "${RED}ERROR: ENABLED_WHISPER_MODELS is not set in your shell environment.${NC}"
            return
        fi
        if [ -z "$OD_MODEL_NAME" ]; then
            echo -e "${RED}ERROR: OD_MODEL_NAME is not set in your shell environment.${NC}"
            return
        fi
    fi
    if [ "$1" != "--summary" ] || [ "$1" != "--all" ]; then
        if [ -z "$EMBEDDING_MODEL_NAME" ]; then
            echo -e "${RED}ERROR: EMBEDDING_MODEL_NAME is not set in your shell environment.${NC}"
            echo -e "${YELLOW}This is required for both SDK and API embedding modes${NC}"
            return
        fi
    fi
    
    # Validate embedding processing mode
    if [[ "$EMBEDDING_PROCESSING_MODE" != "api" && "$EMBEDDING_PROCESSING_MODE" != "sdk" ]]; then
        echo -e "${RED}Invalid EMBEDDING_PROCESSING_MODE: $EMBEDDING_PROCESSING_MODE${NC}"
        echo -e "${YELLOW}Valid options are: 'api' or 'sdk'${NC}"
        return
    fi
    # Enforce dedicated text embedding selection for unified (--all) runs.
    if [ "$1" = "--all" ]; then
        if [ -z "$EMBEDDING_MODEL_NAME" ]; then
            echo -e "${RED}ERROR: EMBEDDING_MODEL_NAME is not set in your shell environment.${NC}"
            return
        elif [ -z "$TEXT_EMBEDDING_MODEL_NAME" ]; then
            echo -e "${RED}ERROR: TEXT_EMBEDDING_MODEL_NAME is not set in your shell environment.${NC}"
            return
        fi

        export EMBEDDING_MODEL_NAME=${TEXT_EMBEDDING_MODEL_NAME}
        echo "Using TEXT_EMBEDDING_MODEL_NAME to override EMBEDDING_MODEL_NAME for --all mode."
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

# Set ACCEL_MOUNT_PATH based on whether /dev/accel/accel0 exists (for NPU)
if [ -e /dev/accel/accel0 ]; then
    export ACCEL_MOUNT_PATH="/dev/accel/accel0"
    echo -e "${GREEN}/dev/accel/accel0 found. NPU device available.${NC}"
else
    export ACCEL_MOUNT_PATH="/dev/null"
    echo -e "${YELLOW}/dev/accel/accel0 not found, NPU not available.${NC}"
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

get_ovms_cache_size() {
    local target_device="$1"
    case "$target_device" in
        *GPU*|*NPU*)
            echo "2"
            ;;
        *)
            echo "10"
            ;;
    esac
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

ovms_config_has_model() {
    local config_path="$1"
    local model_name="$2"

    python3 - "$config_path" "$model_name" <<'PY'
import json
import sys

config_path, model_name = sys.argv[1:3]

try:
    with open(config_path, encoding="utf-8") as config_file:
        config = json.load(config_file)
except Exception:
    raise SystemExit(1)

def contains_model(node):
    if isinstance(node, dict):
        if node.get("name") == model_name:
            return True
        return any(contains_model(value) for value in node.values())
    if isinstance(node, list):
        return any(contains_model(item) for item in node)
    return False

raise SystemExit(0 if contains_model(config) else 1)
PY
}

# Function to reset OVMS config.json to only include specified models
# This ensures stale models from previous runs are removed
reset_ovms_config() {
    local ovms_model_config="${OVMS_CONFIG_DIR}/models/config.json"
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

# Function to export and save requested model for OVMS
# Uses storage-aware naming: {model}_{device}_{format} to allow multiple configs
export_model_for_ovms() {
    local source_model="$1"
    local target_device="$2"
    local weight_format="$3"
    local pipeline_type="$4"
    local cache_size="$5"
    local extra_args=()
    local export_status
    local storage_model_name

    if [ -z "$source_model" ]; then
        echo -e "${RED}ERROR: Missing source model for OVMS export.${NC}"
        return 1
    fi

    # Generate storage-aware model name that includes device and format
    storage_model_name=$(get_ovms_storage_model_name "$source_model" "$target_device" "$weight_format")
    echo -e "[ovms-service] ${BLUE}Storage model name: ${YELLOW}${storage_model_name}${NC}"

    if [ -n "$pipeline_type" ]; then
        extra_args+=(--pipeline_type "$pipeline_type")
    fi
    
    # Export storage_model_name so it's available in subshell
    export storage_model_name
    
    (
        mkdir -p "${CONFIG_DIR}/ovms_config"
        cd "${CONFIG_DIR}/ovms_config" || exit 1

        # Always pull latest export_model.py script
        echo -e "Downloading latest export_model.py from OVMS repository..."
        curl -fsSL https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/tags/v2026.1/demos/common/export_models/export_model.py -o export_model.py || exit 1

        echo -e "Creating Python virtual environment for model export..."
        if ! dpkg-query -W -f='${Status}' python3-venv 2>/dev/null | grep -q "ok installed"; then
            echo -e "Installing python3-venv package..."
            sudo apt install -y python3-venv || exit 1
        else
            echo -e "python3-venv is already installed, skipping installation"
        fi

        python3 -m venv ovms_venv || exit 1
        # shellcheck disable=SC1091
        source ovms_venv/bin/activate || exit 1

        # Check if model is from OpenVINO namespace (pre-converted)
        if [[ "$source_model" == OpenVINO/* ]]; then
            echo -e "${GREEN}Model '${source_model}' is from OpenVINO namespace (pre-converted).${NC}"
            echo -e "${YELLOW}Skipping full requirements installation - only need huggingface_hub for download.${NC}"
            
            # Lightweight dependencies: huggingface_hub (<0.27 for huggingface-cli support) and jinja2 (for graph.pbtxt)
            # Note: huggingface_hub 0.27+ deprecated huggingface-cli in favor of 'hf' command
            if ! pip install --no-cache-dir 'huggingface_hub<0.27' jinja2; then
                echo -e "${RED}ERROR: Failed to install minimal dependencies for OpenVINO model.${NC}"
                deactivate
                rm -rf ovms_venv
                exit 1
            fi
        else
            # Full conversion path: install all requirements for optimum-cli conversion
            local ovms_requirements_url="https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/tags/v2026.1/demos/common/export_models/requirements.txt"
            local tmp_requirements
            tmp_requirements=$(mktemp)

            if ! curl -fsSL "$ovms_requirements_url" -o "$tmp_requirements"; then
                echo -e "${RED}ERROR: Failed to download OVMS requirements from ${ovms_requirements_url}.${NC}"
                rm -f "$tmp_requirements"
                deactivate
                rm -rf ovms_venv
                exit 1
            fi

            if ! pip install --no-cache-dir -r "$tmp_requirements"; then
                echo -e "${RED}ERROR: Failed to install OVMS requirements.${NC}"
                rm -f "$tmp_requirements"
                deactivate
                rm -rf ovms_venv
                exit 1
            fi
            rm -f "$tmp_requirements"
        fi

        if [ "$GATED_MODEL" = true ]; then
            pip install --no-cache-dir -U huggingface_hub[hf_xet]==0.36.0 || exit 1
            echo -e "${BLUE}Logging in to Hugging Face to access gated models...${NC}"
            hf auth login --token "$HUGGINGFACE_TOKEN" || exit 1
        fi

        mkdir -p models

        # Use storage_model_name for --model_name to create device/format-specific folder
        # --source_model is the HuggingFace model ID for downloading
        # --model_name is the folder name where it will be stored
        if ! python3 export_model.py text_generation \
            --source_model "$source_model" \
            --model_name "$storage_model_name" \
            --weight-format "$weight_format" \
            --config_file_path models/config.json \
            --model_repository_path models \
            --target_device "$target_device" \
            --cache_size "$cache_size" \
            "${extra_args[@]}"; then
            echo -e "${RED}ERROR: Failed to export the model '${source_model}' for OVMS.${NC}"
            deactivate
            rm -rf ovms_venv
            exit 1
        fi

        echo -e "Cleaning up virtual environment..."
        deactivate
        rm -rf ovms_venv
    )
    export_status=$?
    if [ $export_status -ne 0 ]; then
        return $export_status
    fi
    
    # Return the storage model name for the caller to use
    echo "$storage_model_name"
}

ensure_ovms_model() {
    local model_name="$1"
    local target_device="$2"
    local weight_format="$3"
    local pipeline_type="$4"
    local ovms_model_config="${OVMS_CONFIG_DIR}/models/config.json"
    local storage_model_name
    local model_path
    local exported_name

    # Generate storage-aware model name (includes device and format)
    storage_model_name=$(get_ovms_storage_model_name "$model_name" "$target_device" "$weight_format")
    model_path="${OVMS_CONFIG_DIR}/models/${storage_model_name}"

    echo -e "[ovms-service] ${BLUE}Checking for model: ${YELLOW}${storage_model_name}${NC}"

    # Check if model folder already exists with this device/format configuration
    if [ -d "$model_path" ] && [ -f "${model_path}/graph.pbtxt" ]; then
        echo -e "[ovms-service] ${GREEN}Model ${YELLOW}${storage_model_name}${GREEN} already exists. Skipping export.${NC}"
        
        # Ensure it's registered in config.json
        if [ -f "${ovms_model_config}" ] && ovms_config_has_model "${ovms_model_config}" "${storage_model_name}"; then
            echo -e "[ovms-service] ${GREEN}Model is registered in OVMS config.${NC}"
        else
            echo -e "[ovms-service] ${YELLOW}Adding model to OVMS config...${NC}"
            # The model exists but config.json doesn't reference it - add it
            add_model_to_ovms_config "${ovms_model_config}" "${storage_model_name}" "${model_path}"
        fi
        
        # Export the storage model name for pipeline-manager
        echo "$storage_model_name"
    else
        echo -e "[ovms-service] ${YELLOW}Model ${RED}${storage_model_name}${YELLOW} not found. Exporting...${NC}"
        
        # Export returns the storage model name
        exported_name=$(export_model_for_ovms \
            "$model_name" \
            "$target_device" \
            "$weight_format" \
            "$pipeline_type" \
            "$(get_ovms_cache_size "$target_device")") || return 1
        
        echo "$exported_name"
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

if [ "$1" = "--summary" ] || [ "$1" = "--all" ]; then
    BACKEND_PROFILE="ovms"

    # Turn on feature flags for summarization and turn off search
    export SUMMARY_FEATURE="FEATURE_ON"
    export SEARCH_FEATURE="FEATURE_OFF"
    export APP_FEATURE_MUX="ATOMIC"

    # If summarization is enabled, set up the environment for OVMS or VLM for summarization
    [ "$1" = "--summary" ] && APP_COMPOSE_FILE="-f docker/compose.base.yaml -f docker/compose.summary.yaml" && \
    echo -e  "[pipeline-manager] ${GREEN}Setting up Video Summarization application${NC}"

    # If no arguments are passed or if --all is passed, set up both summarization and search   
    [ "$1" = "--all" ] && \
    echo -e  "[video-search] ${BLUE}Creating Docker volumes for Video Search services:${NC}" && \
        export SEARCH_FEATURE="FEATURE_ON" && \
        export APP_FEATURE_MUX="SUMMARY_SEARCH" && \
        export VS_INDEX_NAME="video_summary_embeddings" && \
        APP_COMPOSE_FILE="-f docker/compose.base.yaml -f docker/compose.summary.yaml -f docker/compose.search.yaml" && \
        if [ "$ENABLE_VSS_COLLECTOR" = true ]; then
            APP_COMPOSE_FILE="$APP_COMPOSE_FILE -f docker/compose.telemetry.yaml"
            echo -e  "[telemetry] ${GREEN}vss-collector enabled (set ENABLE_VSS_COLLECTOR=true to keep enabled)${NC}"
        else
            echo -e  "[telemetry] ${YELLOW}vss-collector disabled (set ENABLE_VSS_COLLECTOR=true to enable)${NC}"
        fi && \
    echo -e  "[pipeline-manager] ${GREEN}Setting up both applications: Video Summarization and Video Search${NC}"
    
    # Create YOLOX models volume for all modes that include search functionality
    if [ "$1" = "--all" ] && [ "$2" != "config" ]; then
        if ! docker volume ls | grep -q "${YOLOX_MODELS_VOLUME_NAME}"; then
            echo -e "[vdms-dataprep] ${BLUE}Creating Docker volume for YOLOX models: ${YOLOX_MODELS_VOLUME_NAME}${NC}"
            docker volume create "${YOLOX_MODELS_VOLUME_NAME}"
            if [ $? = 0 ]; then
                echo -e "[vdms-dataprep] ${GREEN}YOLOX models volume created successfully${NC}"
            else
                echo -e "[vdms-dataprep] ${RED}ERROR: Failed to create YOLOX models volume${NC}"
                return 1
            fi
        else
            echo -e "[vdms-dataprep] ${GREEN}YOLOX models volume already exists: ${YOLOX_MODELS_VOLUME_NAME}${NC}"
        fi

        # Create ov-models volume for embedding models if it doesn't exist
        if ! docker volume ls | grep -q "ov-models"; then
            echo -e "[multimodal-embedding-serving] ${BLUE}Creating Docker volume for ov-models${NC}"
            docker volume create ov-models
            if [ $? = 0 ]; then
                echo -e "[multimodal-embedding-serving] ${GREEN}ov-models volume created successfully${NC}"
            else
                echo -e "[multimodal-embedding-serving] ${RED}ERROR: Failed to create ov-models volume${NC}"
                return 1
            fi
        else
            echo -e "[multimodal-embedding-serving] ${GREEN}ov-models volume already exists${NC}"
        fi

        # Create data-prep volume if it doesn't exist
        if ! docker volume ls | grep -q "data-prep"; then
            echo -e "[vdms-dataprep] ${BLUE}Creating Docker volume for data-prep${NC}"
            docker volume create data-prep
            if [ $? = 0 ]; then
                echo -e "[vdms-dataprep] ${GREEN}data-prep volume created successfully${NC}"
            else
                echo -e "[vdms-dataprep] ${RED}ERROR: Failed to create data-prep volume${NC}"
                return 1
            fi
        else
            echo -e "[vdms-dataprep] ${GREEN}data-prep volume already exists${NC}"
        fi
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

    configured_ovms_llm_model=${OVMS_LLM_MODEL_NAME:-${LLM_MODEL_NAME}}
    BACKEND_PROFILE_ARGS="--profile ovms"

    if [ "$ENABLE_VLLM" = true ]; then
        echo -e "[vllm-cpu-service] ${BLUE}Using vLLM for both chunk captioning and final summary${NC}"
        BACKEND_PROFILE_ARGS="--profile vllm"
        export USE_VLLM=CONFIG_ON
        export LLM_SUMMARIZATION_API=${VLLM_ENDPOINT}
        export VLM_ENDPOINT=${VLLM_ENDPOINT}
        export VLM_HOST=${VLLM_HOST}
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
        export USE_VLLM=CONFIG_OFF
        export LLM_MODEL_NAME=${configured_ovms_llm_model}
        export LLM_SUMMARIZATION_API=http://$OVMS_HOST/v3
        export VLM_ENDPOINT=http://$OVMS_HOST/v3
        export VLM_HOST=${OVMS_HOST}

        # VLM_TARGET_DEVICE and LLM_TARGET_DEVICE support: CPU, GPU, NPU, HETERO:...
        # (defaults already set at top of script)
        
        # Determine weight format: user override takes precedence, otherwise auto-detect based on device
        export VLM_COMPRESSION_WEIGHT_FORMAT=${VLM_COMPRESSION_WEIGHT_FORMAT:-$(get_ovms_weight_format "$VLM_TARGET_DEVICE")}
        export LLM_COMPRESSION_WEIGHT_FORMAT=${LLM_COMPRESSION_WEIGHT_FORMAT:-$(get_ovms_weight_format "$LLM_TARGET_DEVICE")}

        echo -e "[ovms-service] ${BLUE}VLM Target Device: ${YELLOW}${VLM_TARGET_DEVICE}${NC} (weight format: ${VLM_COMPRESSION_WEIGHT_FORMAT})"
        echo -e "[ovms-service] ${BLUE}LLM Target Device: ${YELLOW}${LLM_TARGET_DEVICE}${NC} (weight format: ${LLM_COMPRESSION_WEIGHT_FORMAT})"

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
        if [ -n "$LLM_MODEL_NAME" ] && [ "$LLM_MODEL_NAME" != "$VLM_MODEL_NAME" ]; then
            ovms_split_model=true
            echo -e "[ovms-service] ${BLUE}Using split-model OVMS mode: VLM=${VLM_MODEL_NAME}, LLM=${LLM_MODEL_NAME}${NC}"
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
        
        echo -e "[ovms-service] ${GREEN}VLM Storage Model: ${YELLOW}${VLM_STORAGE_MODEL_NAME}${NC}"
        echo -e "[ovms-service] ${GREEN}LLM Storage Model: ${YELLOW}${LLM_STORAGE_MODEL_NAME}${NC}"

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

    # if config is passed, set the command to only generate the config
    FINAL_ARG="up -d" && [ "$2" = "config" ] && FINAL_ARG="config"
    DOCKER_COMMAND="docker compose $APP_COMPOSE_FILE $BACKEND_PROFILE_ARGS $FINAL_ARG"

elif [ "$1" = "--search" ]; then
    mkdir -p ${VS_WATCHER_DIR}
    # Turn on feature flags for search and turn off summarization
    export SUMMARY_FEATURE="FEATURE_OFF"
    export SEARCH_FEATURE="FEATURE_ON"
    export APP_FEATURE_MUX="ATOMIC"
    export VS_INDEX_NAME="video_frame_embeddings"  # DB Index or DB Collection name for video search standalone setup

    # Create YOLOX models volume for object detection if it doesn't exist
    if ! docker volume ls | grep -q "${YOLOX_MODELS_VOLUME_NAME}"; then
        echo -e "[vdms-dataprep] ${BLUE}Creating Docker volume for YOLOX models: ${YOLOX_MODELS_VOLUME_NAME}${NC}"
        docker volume create "${YOLOX_MODELS_VOLUME_NAME}"
        if [ $? = 0 ]; then
            echo -e "[vdms-dataprep] ${GREEN}YOLOX models volume created successfully${NC}"
        else
            echo -e "[vdms-dataprep] ${RED}ERROR: Failed to create YOLOX models volume${NC}"
            return 1
        fi
    else
        echo -e "[vdms-dataprep] ${GREEN}YOLOX models volume already exists: ${YOLOX_MODELS_VOLUME_NAME}${NC}"
    fi

    # Create ov-models volume for embedding models if it doesn't exist
    if ! docker volume ls | grep -q "ov-models"; then
        echo -e "[multimodal-embedding-serving] ${BLUE}Creating Docker volume for ov-models${NC}"
        docker volume create ov-models
        if [ $? = 0 ]; then
            echo -e "[multimodal-embedding-serving] ${GREEN}ov-models volume created successfully${NC}"
        else
            echo -e "[multimodal-embedding-serving] ${RED}ERROR: Failed to create ov-models volume${NC}"
            return 1
        fi
    else
        echo -e "[multimodal-embedding-serving] ${GREEN}ov-models volume already exists${NC}"
    fi

    # Create data-prep volume if it doesn't exist
    if ! docker volume ls | grep -q "data-prep"; then
        echo -e "[vdms-dataprep] ${BLUE}Creating Docker volume for data-prep${NC}"
        docker volume create data-prep
        if [ $? = 0 ]; then
            echo -e "[vdms-dataprep] ${GREEN}data-prep volume created successfully${NC}"
        else
            echo -e "[vdms-dataprep] ${RED}ERROR: Failed to create data-prep volume${NC}"
            return 1
        fi
    else
        echo -e "[vdms-dataprep] ${GREEN}data-prep volume already exists${NC}"
    fi

    # If search is enabled, set up video search only
    APP_COMPOSE_FILE="-f docker/compose.base.yaml -f docker/compose.search.yaml"
    if [ "$ENABLE_VSS_COLLECTOR" = true ]; then
        APP_COMPOSE_FILE="$APP_COMPOSE_FILE -f docker/compose.telemetry.yaml"
        echo -e  "[telemetry] ${GREEN}vss-collector enabled (set ENABLE_VSS_COLLECTOR=true to keep enabled)${NC}"
    else
        echo -e  "[telemetry] ${YELLOW}vss-collector disabled (set ENABLE_VSS_COLLECTOR=true to enable)${NC}"
    fi
    echo -e  "[video-search] ${GREEN}Setting up Video Search application${NC}"

    # if config is passed, set the command to only generate the config
    FINAL_ARG="up -d" && [ "$2" = "config" ] && FINAL_ARG="config"
    DOCKER_COMMAND="docker compose $APP_COMPOSE_FILE $FINAL_ARG"
fi

# Run the Docker command to set up the application
if [ -n "$DOCKER_COMMAND" ]; then
    echo -e  "${GREEN}Running Docker command: $DOCKER_COMMAND ${NC}"
    eval "$DOCKER_COMMAND"
else
    echo -e  "No valid setup command provided. Please use --summary, --search, or --all."
fi
if [ $? -ne 0 ]; then
    echo -e "\n${RED}Failed: Some error occured while setting up one or more containers.${NC}"
    return 1
fi
if [ "$2" !=  "config" ]; then
    echo -e "\n${GREEN}Setup completed successfully! 😎"
    echo -e "Access the UI at: ${YELLOW}http://${HOST_IP}:${APP_HOST_PORT}${NC}"
fi
