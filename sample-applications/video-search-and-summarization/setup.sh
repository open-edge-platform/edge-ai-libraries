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
    docker compose -f docker/compose.base.yaml -f docker/compose.summary.yaml -f docker/compose.search.yaml -f docker/compose.telemetry.yaml --profile ovms down
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
export PM_HOST=pipeline-manager
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
    if [ "$ENABLE_OVMS_LLM_SUMMARY" = true ] || [ "$ENABLE_OVMS_LLM_SUMMARY_GPU" = true ]; then
        if [ -z "$OVMS_LLM_MODEL_NAME" ]; then
            echo -e "${RED}ERROR: OVMS_LLM_MODEL_NAME is not set in your shell environment.${NC}"
            return
        fi
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
    mkdir -p ${CONFIG_DIR}/ovms_config
    cd ${CONFIG_DIR}/ovms_config

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

if [ "$1" = "--summary" ] || [ "$1" = "--all" ]; then
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

    # Check if the object detection model directory exists or whether docker-compose config is requested
    if [ ! -d "${OD_MODEL_OUTPUT_DIR}" ] && [ "$2" != "config" ]; then
        echo -e  "[vdms-dataprep] ${YELLOW}Object detection model directory does not exist. Creating it...${NC}"
        mkdir -p "${OD_MODEL_OUTPUT_DIR}"
        convert_object_detection_models
    else
        echo -e  "[vdms-dataprep] ${YELLOW}Object detection model already exists. Skipping model setup...${NC}"
    fi

    # Check if both LLM and VLM are configured for GPU. In which case, prioritize VLM for GPU and set OVMS to CPU
    if [ "$ENABLE_OVMS_LLM_SUMMARY_GPU" = true ] && \ 
       [ "$ENABLE_VLM_GPU" = true ]; then
        echo -e "[ovms-service] ${BLUE}Both VLM and LLM are configured for GPU. Resetting OVMS to run on CPU${NC}"
        export ENABLE_OVMS_LLM_SUMMARY_GPU="false"        
    fi

    # If OVMS is to be used for summarization, set up the environment variables and compose files accordingly
    if [ "$ENABLE_OVMS_LLM_SUMMARY" = true ] || [ "$ENABLE_OVMS_LLM_SUMMARY_GPU" = true ]; then
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

        # If config is passed, set the command to only generate the config
        #FINAL_ARG="up -d" && [ "$2" = "config" ] && FINAL_ARG="config"
        #DOCKER_COMMAND="docker compose $APP_COMPOSE_FILE $FINAL_ARG"

    else
        echo -e "[vlm-openvino-serving] ${BLUE}Using VLM for generating final summary for the video${NC}"
        export USE_OVMS_CONFIG=CONFIG_OFF
        export LLM_SUMMARIZATION_API=http://$VLM_HOST:8000/v1
    fi

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

    # if config is passed, set the command to only generate the config
    FINAL_ARG="up -d" && [ "$2" = "config" ] && FINAL_ARG="config"
    DOCKER_COMMAND="docker compose $APP_COMPOSE_FILE $FINAL_ARG"

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
