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
    docker compose -f docker/compose.base.yaml -f docker/compose.summary.yaml -f docker/compose.search.yaml --profile ovms down
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
    stop_containers
    return $?

elif [ "$1" = "--clean-data" ]; then
    # If --clean-data is passed, bring down the Docker containers and remove volumes
    stop_containers
    if [ $? -ne 0 ]; then
        return 1
    fi
    
    echo -e "${YELLOW}Removing Docker volumes created by the application... ${NC}"

    # Remove volumes 
    docker volume rm docker_minio_data docker_pg_data docker_vdms-db docker_audio_analyzer_data docker_data-prep  2>/dev/null || true
    
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
    echo -e "${GREEN}Using custom OpenVINO configuration: ${YELLOW}$OV_CONFIG${NC}"
else
    unset OV_CONFIG
    # Default configuration will be handled by the VLM service
    echo -e "${GREEN}Using default OpenVINO configuration: ${YELLOW}{\"PERFORMANCE_HINT\": \"LATENCY\"}${NC}"
fi

# env for pipeline-manager
export PM_HOST_PORT=3001
export PM_HOST=pipeline-manager
export PM_SUMMARIZATION_MAX_COMPLETION_TOKENS=4000
export PM_CAPTIONING_MAX_COMPLETION_TOKENS=1024
export PM_LLM_CONCURRENT=2
export PM_VLM_CONCURRENT=4
export PM_MULTI_FRAME_COUNT=12
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

# env for vclip-embedding-ms
export VCLIP_HOST_PORT=9777
export VCLIP_MODEL=${VCLIP_MODEL}
export QWEN_MODEL=${QWEN_MODEL}
export VCLIP_START_OFFSET_SEC=0
export VCLIP_CLIP_DURATION=15
export VCLIP_NUM_FRAMES=64
export VCLIP_DEVICE=${VCLIP_DEVICE:-CPU}
export VCLIP_USE_OV=false
# Set VCLIP_USE_OV to true if VCLIP_DEVICE is GPU
if [ "$ENABLE_EMBEDDING_GPU" = true ]; then
    export VCLIP_DEVICE=GPU
    export VCLIP_USE_OV=true
    echo -e "${BLUE}VCLIP-EMBEDDING-MS will use OpenVINO on GPU${NC}"
fi
export VCLIP_HOST=vclip-embedding-ms
export VCLIP_ENDPOINT=http://$VCLIP_HOST:8000/embeddings

# env for video-search
export VS_HOST_PORT=7890
export VS_WATCHER_DIR=${VS_WATCHER_DIR:-$PWD/data}
export VS_DELETE_PROCESSED_FILES=${VS_DELETE_PROCESSED_FILES:-false}
export VS_INITIAL_DUMP=${VS_INITIAL_DUMP:-false}
export VS_WATCH_DIRECTORY_RECURSIVE=${VS_WATCH_DIRECTORY_RECURSIVE:-false}
export VS_DEFAULT_CLIP_DURATION=15
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

# Object detection model settings
export OD_MODEL_NAME=${OD_MODEL_NAME}
export OD_MODEL_TYPE=${OD_MODEL_TYPE:-"yolo_v8"}
export OD_MODEL_OUTPUT_DIR=${OV_MODEL_DIR}/yoloworld
echo -e "${GREEN}Using object detection model: ${YELLOW}$OD_MODEL_NAME of type $OD_MODEL_TYPE ${NC}"
echo -e "${GREEN}Output directory for object detection model: ${YELLOW}$OD_MODEL_OUTPUT_DIR ${NC}"


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
        if [ -z "$VCLIP_MODEL" ]; then
            echo -e "${RED}ERROR: VCLIP_MODEL is not set in your shell environment.${NC}"
            return
        elif [ "$VCLIP_MODEL" != "openai/clip-vit-base-patch32" ]; then
            echo -e "${RED}ERROR: VCLIP_MODEL is set to an invalid value. Expected: 'openai/clip-vit-base-patch32'.${NC}"
            return
        fi
    fi
    if [ "$1" = "--all" ]; then
        if [ -z "$VCLIP_MODEL" ]; then
            echo -e "${RED}ERROR: VCLIP_MODEL is not set in your shell environment.${NC}"
            return
        elif [ -z "$QWEN_MODEL" ] || [ "$QWEN_MODEL" != "Qwen/Qwen3-Embedding-0.6B" ]; then
            echo -e "${RED}ERROR: QWEN_MODEL is either not set or set to invalid value in your shell environment.${NC}"
            return
        fi
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
    pip install -q "openvino>=2025.0.0" "nncf>=2.9.0"
    pip install -q "torch>=2.1" "torchvision>=0.16" "ultralytics==8.3.59" onnx tqdm opencv-python --extra-index-url https://download.pytorch.org/whl/cpu
    
    # Create model conversion script

    echo -e  "Converting object detection model: ${OD_MODEL_NAME} (${OD_MODEL_TYPE})..."
    python3 video-ingestion/resources/scripts/converter.py --model-name "${OD_MODEL_NAME}" --model-type "${OD_MODEL_TYPE}" --output-dir "${OD_MODEL_OUTPUT_DIR}"

    echo -e  "Model conversion completed. Cleaning up..."
    deactivate
    rm -rf ov_model_venv
    echo -e  "Object detection model ${OD_MODEL_NAME} has been successfully converted and saved to ${OD_MODEL_OUTPUT_DIR}"
}

# Function to export and save requested model for OVMS
export_model_for_ovms() {
    # Create a directory for model, model_export.py script and virtual environment
    curr_dir=$(pwd)
    mkdir -p ${CONFIG_DIR}/ovms_config
    cd ${CONFIG_DIR}/ovms_config

    # Download the OVMS model export script
    if [ ! -f export_model.py ]; then
        curl https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/heads/releases/2025/1/demos/common/export_models/export_model.py -o export_model.py
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
    pip install --no-cache-dir -r https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/heads/releases/2025/1/demos/common/export_models/requirements.txt
    if [ "$GATED_MODEL" = true ]; then
        pip install --no-cache-dir huggingface-hub  # Install huggingface-hub for downloading gated models
        echo -e "${BLUE}Logging in to Hugging Face to access gated models...${NC}"
        huggingface-cli login --token $HUGGINGFACE_TOKEN  # Login to Hugging Face using the provided token
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
        echo -e  "${GREEN}Setting up Video Summarization application${NC}"

    # If no arguments are passed or if --all is passed, set up both summarization and search   
    [ "$1" = "--all" ] && \
        echo -e  "${BLUE}Creating Docker volumes for Video Search services:${NC}" && \
        export SEARCH_FEATURE="FEATURE_ON" && \
        export USE_ONLY_TEXT_EMBEDDINGS=True && \
        export APP_FEATURE_MUX="SUMMARY_SEARCH" && \
        export VS_INDEX_NAME="video_summary_embeddings" && \
        APP_COMPOSE_FILE="-f docker/compose.base.yaml -f docker/compose.summary.yaml -f docker/compose.search.yaml" && \
        echo -e  "${GREEN}Setting up both applications: Video Summarization and Video Search${NC}"

    # Check if the object detection model directory exists or whether docker-compose config is requested
    if [ ! -d "${OD_MODEL_OUTPUT_DIR}" ] && [ "$2" != "config" ]; then
        echo -e  "${YELLOW}Object detection model directory does not exist. Creating it...${NC}"
        mkdir -p "${OD_MODEL_OUTPUT_DIR}"
        convert_object_detection_models
    else
        echo -e  "${YELLOW}Object detection model already exists. Skipping model setup...${NC}"
    fi

    # If OVMS is to be used for summarization, set up the environment variables and compose files accordingly
    if [ "$ENABLE_OVMS_LLM_SUMMARY" = true ] || [ "$ENABLE_OVMS_LLM_SUMMARY_GPU" = true ]; then
        echo -e "${BLUE}Using OVMS for generating final summary for the video${NC}"
        export USE_OVMS_CONFIG=CONFIG_ON
        export LLM_SUMMARIZATION_API=http://$OVMS_HOST/v3
        export LLM_MODEL_API="v1/config"

        # Set relevant variables, compose files and profiles based on whether GPU is used or not
        if [ "$ENABLE_OVMS_LLM_SUMMARY_GPU" = true ]; then
            echo -e "${BLUE}Using GPU acceleration for OVMS${NC}"
            export OVMS_CACHE_SIZE=2
            export LLM_COMPRESSION_WEIGHT_FORMAT=int4
            export LLM_DEVICE=GPU
            APP_COMPOSE_FILE="$APP_COMPOSE_FILE -f docker/compose.gpu_ovms.yaml --profile ovms"
        else
            echo -e "${BLUE}Running OVMS on CPU${NC}"
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
                echo -e "${YELLOW}No existing model configurations found. Exporting model ${RED}${OVMS_LLM_MODEL_NAME}${YELLOW}...${NC}"
                needs_export=true
            # Check whether the model exists in OVMS config
            elif grep -q ${OVMS_LLM_MODEL_NAME} "${ovms_model_config}"; then
                echo -e "${YELLOW}Model ${RED}${OVMS_LLM_MODEL_NAME}${YELLOW} exists in OVMS config. Checking device type...${NC}"
                # If model exists, check if device type matches
                if [ -f "${device_marker_file}" ]; then
                    saved_device=$(cat "${device_marker_file}")
                    if [ "${saved_device}" != "${LLM_DEVICE}" ]; then
                        echo -e "${YELLOW}Model was exported for ${RED}${saved_device}${YELLOW}. Re-exporting model for ${RED}${LLM_DEVICE}${YELLOW}...${NC}"
                        needs_export=true
                    else
                        echo -e "${YELLOW}Model was exported for ${RED}${LLM_DEVICE}${YELLOW}. Skipping model setup...${NC}"
                    fi
                else
                    echo -e "${YELLOW}Device type information missing. Re-exporting model...${NC}"
                    needs_export=true
                fi
            else
                echo -e "${YELLOW}Model ${RED}${OVMS_LLM_MODEL_NAME}${YELLOW} not found in OVMS config. Exporting model...${NC}"
                needs_export=true
            fi
            
            # Export model if needed
            if [ "$needs_export" = true ]; then
                export_model_for_ovms
            fi
        fi

        # If config is passed, set the command to only generate the config
        FINAL_ARG="up -d" && [ "$2" = "config" ] && FINAL_ARG="config"
        DOCKER_COMMAND="docker compose $APP_COMPOSE_FILE $FINAL_ARG"

    else
        echo -e "${BLUE}Using VLM for generating final summary for the video${NC}"
        export USE_OVMS_CONFIG=CONFIG_OFF
        export LLM_SUMMARIZATION_API=http://$VLM_HOST:8000/v1

        if [ "$ENABLE_VLM_GPU" = true ]; then
            export VLM_DEVICE=GPU
            export PM_VLM_CONCURRENT=1
            export PM_LLM_CONCURRENT=1
            export VLM_COMPRESSION_WEIGHT_FORMAT=int4
            export PM_MULTI_FRAME_COUNT=6
            export WORKERS=1
            echo -e "${BLUE}Using VLM for summarization on GPU${NC}"
        else
            export VLM_DEVICE=CPU
            echo -e "${BLUE}Using VLM for summarization on CPU${NC}"
        fi

        # if config is passed, set the command to only generate the config
        FINAL_ARG="up -d" && [ "$2" = "config" ] && FINAL_ARG="config"
        DOCKER_COMMAND="docker compose $APP_COMPOSE_FILE $FINAL_ARG"
    fi

elif [ "$1" = "--search" ]; then
    mkdir -p ${VS_WATCHER_DIR}
    # Turn on feature flags for search and turn off summarization
    export SUMMARY_FEATURE="FEATURE_OFF"
    export SEARCH_FEATURE="FEATURE_ON"
    export APP_FEATURE_MUX="ATOMIC"
    export USE_ONLY_TEXT_EMBEDDINGS=False  # When only search is enabled, we use both text and video embeddings
    export VS_INDEX_NAME="video_frame_embeddings"  # DB Index or DB Collection name for video search standalone setup

    # If search is enabled, set up video search only
    APP_COMPOSE_FILE="-f docker/compose.base.yaml -f docker/compose.search.yaml" 
    echo -e  "${GREEN}Setting up Video Search application${NC}"

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