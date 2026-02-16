#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
# Sets required environment variable to run the VDMS-DataPrep microservice along with all dependencies.
# Change these values as required.

# Color codes for terminal output
RED='\033[0;31m'
NC='\033[0m'

# Common env vars ---------------------------------------------------
export PROJECT_NAME=${PROJECT_NAME}
export COVERAGE_REQ=80
export PROJ_TEST_DIR=./tests
host_ip=$(ip route get 1 | awk '{print $7}')
export HOST_IP=${HOST_IP:-$host_ip}
export TAG=${TAG:-latest}

# Env vars for vdms-dataprep -----------------------------------------
export INDEX_NAME="video-rag"
export DEFAULT_BUCKET_NAME="vdms-bucket"
export VDMS_DATAPREP_HOST_PORT=6007

# Embedding and processing configuration -----------------------------
export EMBEDDING_PROCESSING_MODE=${EMBEDDING_PROCESSING_MODE:-"sdk"}
export SDK_USE_OPENVINO=${SDK_USE_OPENVINO:-true}
export VDMS_DATAPREP_DEVICE=${VDMS_DATAPREP_DEVICE:-"CPU"}
export OV_MODELS_DIR=${OV_MODELS_DIR:-"/app/ov_models"}
export EMBEDDING_OV_MODELS_DIR=${EMBEDDING_OV_MODELS_DIR:-$OV_MODELS_DIR}
export EMBEDDING_DEVICE=${EMBEDDING_DEVICE:-$VDMS_DATAPREP_DEVICE}
export OV_PERFORMANCE_MODE=${OV_PERFORMANCE_MODE:-"THROUGHPUT"}
export FRAME_INTERVAL=${FRAME_INTERVAL:-15}
export ENABLE_OBJECT_DETECTION=${ENABLE_OBJECT_DETECTION:-true}
export DETECTION_CONFIDENCE=${DETECTION_CONFIDENCE:-0.85}
export ROI_CONSOLIDATION_ENABLED=${ROI_CONSOLIDATION_ENABLED:-false}
export ROI_CONSOLIDATION_IOU_THRESHOLD=${ROI_CONSOLIDATION_IOU_THRESHOLD:-0.2}
export ROI_CONSOLIDATION_CLASS_AWARE=${ROI_CONSOLIDATION_CLASS_AWARE:-false}
export ROI_CONSOLIDATION_CONTEXT_SCALE=${ROI_CONSOLIDATION_CONTEXT_SCALE:-0.2}
export FRAMES_TEMP_DIR=${FRAMES_TEMP_DIR:-"/tmp/dataprep"}
export VDMS_DATAPREP_LOG_LEVEL=${VDMS_DATAPREP_LOG_LEVEL:-INFO}
# Optional hard cap for SDK parallel workers (auto when unset)
export MAX_PARALLEL_WORKERS=${MAX_PARALLEL_WORKERS:-""}
export EMBEDDING_BATCH_SIZE=${EMBEDDING_BATCH_SIZE:-32}

# Embedding microservice configuration -------------------------------
export EMBEDDING_SERVER_PORT=${EMBEDDING_SERVER_PORT:-9777}
export EMBEDDING_MODEL_NAME=${EMBEDDING_MODEL_NAME}
export EMBEDDING_USE_OV=${EMBEDDING_USE_OV:-$SDK_USE_OPENVINO}
export DEFAULT_START_OFFSET_SEC=${DEFAULT_START_OFFSET_SEC:-0}
export DEFAULT_CLIP_DURATION=${DEFAULT_CLIP_DURATION:--1}
export DEFAULT_NUM_FRAMES=${DEFAULT_NUM_FRAMES:-64}
export MULTIMODAL_EMBEDDING_ENDPOINT=${MULTIMODAL_EMBEDDING_ENDPOINT:-"http://multimodal-embedding-serving:8000/embeddings"}

# System user / group identifiers -----------------------------------
export USER_ID=$(id -u)
export USER_GROUP_ID=$(id -g)
export VIDEO_GROUP_ID=$(getent group video | awk -F: '{printf "%s\n", $3}')
export RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')

# Model storage configuration for object detection
export YOLOX_MODELS_VOLUME_NAME="vdms-yolox-models"
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
if [ "$1" != "--down" ] && [ "$1" != "--build" ] && [ "$1" != "--build-dev" ] && [ "$1" != "--build-test" ] && [ "$1" != "--build-lint" ]; then
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
add_no_proxy_host "multimodal-embedding-serving"
export no_proxy_env=${no_proxy}

# Run linter
if [ "$1" = "lint" ] && [ $# -ge 1 ] && [ $# -le 2 ]; then
    if ! [ "$2" = "" ] && ! [ "$2" = "-a" ] && ! [ "$2" = "--apply" ]; then
        echo "Invalid flag provided!"
        return
    fi
    . ./scripts/linter.sh "$2"

# Run tests
elif [ "$1" = "test" ] && [ $# -ge 1 ] && [ $# -le 2 ]; then
    . ./scripts/tester.sh "$2"

# Set environment variables on shell without spinning up any container
elif [ "$1" = "--nosetup" ] && [ "$#" -eq 1 ]; then
    echo "All environment variables set successfully!"
    return

# Check configuration values for docker compose
elif [ "$1" = "--conf" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml config

elif [ "$1" = "--conf-dev" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml -f docker/compose-dev.yaml config

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
    default_image="${REGISTRY}vdms-dataprep:${TAG:-latest}"
    if ./build.sh; then
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

# Build dataprep dev image
elif [ "$1" = "--build-dev" ] && ([ "$#" -eq 1 ] || [ "$#" -eq 2 ]); then
    tag=${2:-intelgai/vdms-dataprep:dev}
    docker build -t $tag -f docker/Dockerfile --target dev .
    if [ $? = 0 ]; then
        docker images | grep $tag
        echo "Dev Image ${tag} was successfully built."
    fi

# Build the dataprep image after linting checks.
elif [ "$1" = "--build-lint" ] && ([ "$#" -eq 1 ] || [ "$#" -eq 2 ]); then
    tag=${2:-intelgai/vdms-dataprep:dev}

    # Build the image targeting the lint stage
    docker build -t $tag -f docker/Dockerfile --target lint .
    
    if [ $? = 0 ]; then
        docker images | grep $tag
        echo "Linter image ${tag} was successfully built."
    fi


# Build the image after running and passing tests
elif [ "$1" = "--build-test" ] && ([ "$#" -eq 1 ] || [ "$#" -eq 2 ]); then
    tag=${2:-intelgai/vdms-dataprep:final-dev}

    # Build the image targeting the test stage
    docker build --build-arg COVERAGE_REQ -t $tag -f docker/Dockerfile --target final-dev .

    if [ $? = 0 ]; then
        docker images | grep $tag
        echo "Final-dev image ${tag} was successfully built."
    fi

# Build, generates and serve coverage report
elif [ "$1" = "--build-report" ] && ([ "$#" -eq 1 ] || [ "$#" -eq 2 ]); then
    tag=${2:-intelgai/vdms-dataprep:covreport}
    reporter_container=intelgai-vdms-dataprep-report

    # Build the image targeting the test stage
    docker build --build-arg COVERAGE_REQ -t $tag -f docker/Dockerfile --target report .

    # Run the report server
    if [ $? = 0 ]; then
        docker images | grep $tag
        echo "Reporter image ${tag} was successfully built."
        docker run --rm -p "8899:8899" --name $reporter_container $tag
        docker stop $reporter_container
    fi

# Spin-up all services with dev env in daemon mode
elif [ "$1" = "--dev" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml -f docker/compose-dev.yaml up -d --build
    if [ $? = 0 ]; then
        docker ps | grep "${PROJECT_NAME}"
        echo "Dev environment is up!"
    fi

# Spin-up all services with dev env with logs showing on STDOUT
elif [ "$1" = "--dev" ] && [ "$2" = "--nd" ] && [ "$#" -eq 2 ]; then
    docker compose -f docker/compose.yaml -f docker/compose-dev.yaml up --build

# Spin-up prod version of all services in non-daemon mode
elif [ "$1" = "--nd" ] && [ "$#" -eq 1 ]; then
    docker compose -f docker/compose.yaml up --build

# Spin-up prod version of all services in daemon mode
elif [ "$#" -eq 0 ]; then
    if ! ./build.sh; then
        echo -e "${RED}ERROR: build.sh failed. Please inspect the build logs.${NC}"
        exit 1
    fi

    docker compose -f docker/compose.yaml up -d --no-build
    if [ $? = 0 ]; then
        docker ps | grep "${PROJECT_NAME}"
        echo "Prod environment is up!"
    fi

else
    echo "Invalid argument!"
fi
