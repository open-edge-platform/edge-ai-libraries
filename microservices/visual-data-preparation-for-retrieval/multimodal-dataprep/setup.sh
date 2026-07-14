#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Sets required environment variable to run the Multimodal DataPrep microservice along with all dependencies.
# Change these values as required.

# Color codes for terminal output
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MICROSERVICES_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
DOCKERFILE="$SCRIPT_DIR/docker/Dockerfile"

# Common env vars ---------------------------------------------------
export PROJECT_NAME=${PROJECT_NAME}
host_ip=$(ip route get 1 | awk '{print $7}')
export HOST_IP=${HOST_IP:-$host_ip}
export TAG=${TAG:-latest}

# Env vars for multimodal-dataprep -----------------------------------------
export INDEX_NAME="video-rag"
export DEFAULT_BUCKET_NAME="vdms-bucket"
export MM_DATAPREP_HOST_PORT=6007

# Embedding configuration -------------------------------------------
export MM_DATAPREP_USE_OPENVINO=${MM_DATAPREP_USE_OPENVINO:-true}
export OV_MODELS_DIR=${OV_MODELS_DIR:-"/app/ov_models"}
export EMBEDDING_OV_MODELS_DIR=${EMBEDDING_OV_MODELS_DIR:-$OV_MODELS_DIR}
# Per-component devices are set independently (no baseline device).
export MM_DATAPREP_EMBEDDING_DEVICE=${MM_DATAPREP_EMBEDDING_DEVICE:-"CPU"}
export MM_DATAPREP_DETECTION_DEVICE=${MM_DATAPREP_DETECTION_DEVICE:-"CPU"}
export MM_DATAPREP_OV_PERFORMANCE_MODE=${MM_DATAPREP_OV_PERFORMANCE_MODE:-"THROUGHPUT"}
export MM_DATAPREP_FRAME_INTERVAL=${MM_DATAPREP_FRAME_INTERVAL:-15}
export MM_DATAPREP_ENABLE_OBJECT_DETECTION=${MM_DATAPREP_ENABLE_OBJECT_DETECTION:-true}
export MM_DATAPREP_DETECTION_CONFIDENCE=${MM_DATAPREP_DETECTION_CONFIDENCE:-0.85}
export MM_DATAPREP_ROI_CONSOLIDATION_ENABLED=${MM_DATAPREP_ROI_CONSOLIDATION_ENABLED:-false}
export MM_DATAPREP_ROI_CONSOLIDATION_IOU_THRESHOLD=${MM_DATAPREP_ROI_CONSOLIDATION_IOU_THRESHOLD:-0.2}
export MM_DATAPREP_ROI_CONSOLIDATION_CLASS_AWARE=${MM_DATAPREP_ROI_CONSOLIDATION_CLASS_AWARE:-false}
export MM_DATAPREP_ROI_CONSOLIDATION_CONTEXT_SCALE=${MM_DATAPREP_ROI_CONSOLIDATION_CONTEXT_SCALE:-0.2}
export MM_DATAPREP_FRAMES_TEMP_DIR=${MM_DATAPREP_FRAMES_TEMP_DIR:-"/tmp/dataprep"}
export MM_DATAPREP_LOG_LEVEL=${MM_DATAPREP_LOG_LEVEL:-INFO}
# Optional hard cap for parallel embedding workers (auto when unset)
export MM_DATAPREP_MAX_PARALLEL_WORKERS=${MM_DATAPREP_MAX_PARALLEL_WORKERS:-""}
export MM_DATAPREP_EMBEDDING_BATCH_SIZE=${MM_DATAPREP_EMBEDDING_BATCH_SIZE:-32}
export MM_DATAPREP_VIDEO_SHM_MAX_BLOCKS=${MM_DATAPREP_VIDEO_SHM_MAX_BLOCKS:-512}
export MM_DATAPREP_VIDEO_SHM_BLOCK_SIZE=${MM_DATAPREP_VIDEO_SHM_BLOCK_SIZE:-$((1920 * 1080 * 3))}
export MM_DATAPREP_VIDEO_EXTRACTION_BATCH_SIZE=${MM_DATAPREP_VIDEO_EXTRACTION_BATCH_SIZE:-256}
export MM_DATAPREP_PIPELINE_QUEUE_MAXSIZE=${MM_DATAPREP_PIPELINE_QUEUE_MAXSIZE:-16}
export MM_DATAPREP_PIPELINE_COMPLETION_QUEUE_MAXSIZE=${MM_DATAPREP_PIPELINE_COMPLETION_QUEUE_MAXSIZE:-1}
export MM_DATAPREP_DETECTION_WORKER_THREADS=${MM_DATAPREP_DETECTION_WORKER_THREADS:-2}
export MM_DATAPREP_EMBED_WORKER_THREADS=${MM_DATAPREP_EMBED_WORKER_THREADS:-2}
export MM_DATAPREP_PIPELINE_QUEUE_GET_TIMEOUT_S=${MM_DATAPREP_PIPELINE_QUEUE_GET_TIMEOUT_S:-1.0}
export MM_DATAPREP_SAVE_RUNTIME_PIPELINE_STATS=${MM_DATAPREP_SAVE_RUNTIME_PIPELINE_STATS:-false}
export MM_DATAPREP_ENABLE_TRACING=${MM_DATAPREP_ENABLE_TRACING:-false}
export MM_DATAPREP_VIDEO_FRAME_DECODER_WORKERS=${MM_DATAPREP_VIDEO_FRAME_DECODER_WORKERS:-2}
export MM_DATAPREP_VIDEO_FRAME_LOG_LEVEL=${MM_DATAPREP_VIDEO_FRAME_LOG_LEVEL:-INFO}

# Embedding model selection (in-process SDK) ------------------------
export EMBEDDING_MODEL_NAME=${EMBEDDING_MODEL_NAME}

# System user / group identifiers -----------------------------------
export USER_ID=$(id -u)
export USER_GROUP_ID=$(id -g)
export VIDEO_GROUP_ID=$(getent group video | awk -F: '{printf "%s\n", $3}')
export RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')

# Set DRI_MOUNT_PATH based on whether /dev/dri exists and is not empty
if [ -d /dev/dri ] && [ "$(ls -A /dev/dri)" ]; then
    export DRI_MOUNT_PATH="/dev/dri"
else
    export DRI_MOUNT_PATH="/dev/null"
fi

# Set ACCEL_MOUNT_PATH based on whether /dev/accel/accel0 exists
if [ -e /dev/accel/accel0 ]; then
    export ACCEL_MOUNT_PATH="/dev/accel/accel0"
else
    export ACCEL_MOUNT_PATH="/dev/null"
fi

# Model storage configuration for object detection
export YOLOX_MODELS_VOLUME_NAME="dataprep-yolox-models"
export YOLOX_MODELS_MOUNT_PATH="/app/models/yolox"


# Env vars for minio service ---------------------------
export MINIO_HOST="minio-server"
# Port on which we want to access API service outside container i.e. on host.
export MINIO_API_HOST_PORT=6010
# Port on which we want to access Minio Console outside container i.e. on host.
export MINIO_CONSOLE_HOST_PORT=6011
# Mount point for Minio objects storage. This helps persist objects stored on minio server.
export MINIO_MOUNT_PATH="/mnt/miniodata"

# Env vars for vdms-vector-db ---------------------------------------
export VDMS_STORAGE=aws
export VDMS_VDB_HOST="vdms-vector-db"
export VDMS_VDB_HOST_PORT=6020

# ----------------------------------------------------------------------------------------
# Following part contains variables that need to be set from shell
# ----------------------------------------------------------------------------------------
# To override value of MINIO_ROOT_USER, set MINIO_ROOT_USER from your shell.
# To override value of MINIO_ROOT_PASSWORD, set MINIO_ROOT_PASSWORD from your shell.
# To override value of REGISTRY, set REGISTRY_URL from shell.

# Username for MINIO Server
export MINIO_ROOT_USER=${MINIO_ROOT_USER}
# Password for Minio Server
export MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}

# If REGISTRY_URL is set, ensure it ends with a trailing slash
# Using parameter expansion to conditionally append '/' if not already present
[[ -n "$REGISTRY_URL" ]] && REGISTRY_URL="${REGISTRY_URL%/}/"

# If PROJECT_NAME is set, ensure it ends with a trailing slash
[[ -n "$PROJECT_NAME" ]] && PROJECT_NAME="${PROJECT_NAME%/}/"

export REGISTRY="${REGISTRY_URL}${PROJECT_NAME}"
echo "Using Registry : ${REGISTRY}"
# -----------------------------------------------------------------------------------------

# Check if MINIO credentials are set
# Only check MinIO credentials if we're not just stopping containers or building images
if [ "$1" != "--down" ] && [ "$1" != "--build" ]; then
    if [ -z "$MINIO_ROOT_USER" ]; then
        echo -e "${RED}ERROR: MINIO_ROOT_USER is not set in environment.${NC}"
        return
    fi

    if [ -z "$MINIO_ROOT_PASSWORD" ]; then
        echo -e "${RED}ERROR: MINIO_ROOT_PASSWORD is not set in environment.${NC}"
        return
    fi
    
    # Create docker volume for YOLOX models if it doesn't exist
    if ! docker volume ls | grep -q "${YOLOX_MODELS_VOLUME_NAME}"; then
        echo "Creating Docker volume for YOLOX models: ${YOLOX_MODELS_VOLUME_NAME}"
        docker volume create "${YOLOX_MODELS_VOLUME_NAME}"
        if [ $? = 0 ]; then
            echo "YOLOX models volume created successfully"
        else
            echo -e "${RED}ERROR: Failed to create YOLOX models volume${NC}"
            return
        fi
    else
        echo "YOLOX models volume already exists: ${YOLOX_MODELS_VOLUME_NAME}"
    fi
fi

#------------------------------------------------------------------------------------------

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

# Updating no_proxy to add required service names. Containers need to bypass proxy while connecting to these services.
add_no_proxy_host "${VDMS_VDB_HOST}"
add_no_proxy_host "${MINIO_HOST}"
export no_proxy_env=${no_proxy}

# Set environment variables on shell without spinning up any container
if [ "$1" = "--nosetup" ] && [ "$#" -eq 1 ]; then
    echo "All environment variables set successfully!"
    return

# Check configuration values for docker compose
elif [ "$1" = "--conf" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml config

# Teardown Everything
elif [ "$1" = "--down" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml down
    if [ $? = 0 ]; then
        echo "All services down!"
        
        # Optional: Remove YOLOX models volume (uncomment if you want to clean up models on teardown)
        # echo "Removing YOLOX models volume: ${YOLOX_MODELS_VOLUME_NAME}"
        # docker volume rm "${YOLOX_MODELS_VOLUME_NAME}" 2>/dev/null || echo "Volume not found or already removed"
    fi

# Build dataprep image
elif [ "$1" = "--build" ] && ([ "$#" -eq 1 ] || [ "$#" -eq 2 ]); then
    default_image="${REGISTRY}multimodal-dataprep:${TAG:-latest}"
    if "$SCRIPT_DIR/build.sh"; then
        docker images | grep "${default_image}"
        echo "Image ${default_image} was successfully built."

        if [ $# -eq 2 ]; then
            custom_tag="$2"
            docker tag "${default_image}" "${custom_tag}"
            echo "Tagged image ${default_image} as ${custom_tag}."
        fi
    else
        echo -e "${RED}ERROR: build.sh failed. Please check the build logs for details.${NC}"
    fi

# Spin-up all services in non-daemon mode (logs on STDOUT)
elif [ "$1" = "--nd" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml up --build

# Default: export environment variables (and ensure YOLOX volume exists) without building or starting containers
elif [ "$#" -eq 0 ]; then
    echo "All environment variables set successfully!"

else
    echo "Invalid argument!"
fi
