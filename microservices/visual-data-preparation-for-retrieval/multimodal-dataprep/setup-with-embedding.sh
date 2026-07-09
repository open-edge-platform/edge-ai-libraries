#!/bin/bash

# Combined setup for Multimodal DataPrep and Multimodal Embedding Microservice
# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Color codes for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Common env vars ---------------------------------------------------
export PROJECT_NAME=${PROJECT_NAME}
host_ip=$(ip route get 1 | awk '{print $7}')
export HOST_IP=$host_ip
export TAG=${TAG:-latest}

# Registry handling
[[ -n "$REGISTRY_URL" ]] && REGISTRY_URL="${REGISTRY_URL%/}/"
export REGISTRY="${REGISTRY_URL}${PROJECT_NAME}"
echo -e "${GREEN}Using Registry : ${YELLOW}$REGISTRY ${NC}"
export no_proxy=${no_proxy},multimodal-embedding-serving,minio-server,vdms-vector-db
export no_proxy_env=${no_proxy}
# Env vars for minio service ---------------------------
export MINIO_HOST="minio-server"
export MINIO_API_HOST_PORT=6010
export MINIO_CONSOLE_HOST_PORT=6011
export MINIO_MOUNT_PATH="/mnt/miniodata"
export MINIO_ROOT_USER=${MINIO_ROOT_USER}
export MINIO_ROOT_PASSWORD=${MINIO_ROOT_PASSWORD}

# Env vars for vdms-vector-db ---------------------------------------
export VDMS_STORAGE=aws
export VDMS_VDB_HOST="vdms-vector-db"
export VDMS_VDB_HOST_PORT=6020

# Env vars for multimodal-dataprep -----------------------------------------
export INDEX_NAME="video-rag"
export DEFAULT_BUCKET_NAME="vdms-bucket"
export MM_DATAPREP_HOST_PORT=6007
export YOLOX_MODELS_VOLUME_NAME="dataprep-yolox-models"
export YOLOX_MODELS_MOUNT_PATH="/app/models/yolox"

# Embedding configuration
# Note: EMBEDDING_MODEL_NAME is used for model selection
export MM_DATAPREP_USE_OPENVINO=${MM_DATAPREP_USE_OPENVINO:-true}
export OV_MODELS_DIR=${OV_MODELS_DIR:-"/app/ov_models"}
export EMBEDDING_OV_MODELS_DIR=${EMBEDDING_OV_MODELS_DIR:-$OV_MODELS_DIR}
export MM_OV_PERFORMANCE_MODE=${MM_OV_PERFORMANCE_MODE:-"THROUGHPUT"}

# Device configuration ------------------------------------------------------
# Each component's device is configured independently; there is no baseline
# device. Defaults to CPU when a variable is not explicitly set.
#   MM_EMBEDDING_DEVICE          -> DataPrep in-process embedding pipeline
#   MM_DATAPREP_DETECTION_DEVICE -> DataPrep object detection
#   EMBEDDING_DEVICE             -> Multimodal Embedding (MME) service
export MM_EMBEDDING_DEVICE=${MM_EMBEDDING_DEVICE:-"CPU"}
export MM_DATAPREP_DETECTION_DEVICE=${MM_DATAPREP_DETECTION_DEVICE:-"CPU"}
export EMBEDDING_DEVICE=${EMBEDDING_DEVICE:-"CPU"}

# If any component targets the GPU, verify Intel GPU availability once.
check_gpu_availability() {
    echo -e "${YELLOW}⚙️  GPU device requested — verifying Intel GPU availability...${NC}"
    if ! lspci | grep -i "vga.*intel" > /dev/null 2>&1; then
        echo -e "${RED}Warning: No Intel GPU detected. GPU mode may not work properly.${NC}"
    else
        echo -e "${GREEN}Intel GPU detected${NC}"
    fi
    if [[ ! -d "/dev/dri" ]]; then
        echo -e "${RED}Warning: /dev/dri not found. GPU acceleration may not be available.${NC}"
    else
        echo -e "${GREEN}DRI devices found for GPU acceleration${NC}"
    fi
}
if [[ "${MM_EMBEDDING_DEVICE}" == "GPU" || "${MM_DATAPREP_DETECTION_DEVICE}" == "GPU" || "${EMBEDDING_DEVICE}" == "GPU" ]]; then
    check_gpu_availability
fi

# Frame processing settings
export FRAME_INTERVAL=${FRAME_INTERVAL:-15}
export ENABLE_OBJECT_DETECTION=${ENABLE_OBJECT_DETECTION:-true}
export DETECTION_CONFIDENCE=${DETECTION_CONFIDENCE:-0.85}
export ROI_CONSOLIDATION_ENABLED=${ROI_CONSOLIDATION_ENABLED:-false}
export ROI_CONSOLIDATION_IOU_THRESHOLD=${ROI_CONSOLIDATION_IOU_THRESHOLD:-0.2}
export ROI_CONSOLIDATION_CLASS_AWARE=${ROI_CONSOLIDATION_CLASS_AWARE:-false}
export ROI_CONSOLIDATION_CONTEXT_SCALE=${ROI_CONSOLIDATION_CONTEXT_SCALE:-0.2}
export FRAMES_TEMP_DIR=${FRAMES_TEMP_DIR:-"/tmp/dataprep"}

# Application configuration
export MM_DATAPREP_LOG_LEVEL=${MM_DATAPREP_LOG_LEVEL:-INFO}
export MAX_PARALLEL_WORKERS=${MAX_PARALLEL_WORKERS:-""}
export EMBEDDING_BATCH_SIZE=${EMBEDDING_BATCH_SIZE:-32}
export MM_DATAPREP_VIDEO_SHM_MAX_BLOCKS=${MM_DATAPREP_VIDEO_SHM_MAX_BLOCKS:-512}
export MM_DATAPREP_VIDEO_SHM_BLOCK_SIZE=${MM_DATAPREP_VIDEO_SHM_BLOCK_SIZE:-$((1920 * 1080 * 3))}
export MM_DATAPREP_VIDEO_EXTRACTION_BATCH_SIZE=${MM_DATAPREP_VIDEO_EXTRACTION_BATCH_SIZE:-256}
export MM_DATAPREP_PIPELINE_QUEUE_MAXSIZE=${MM_DATAPREP_PIPELINE_QUEUE_MAXSIZE:-16}
export MM_DATAPREP_PIPELINE_COMPLETION_QUEUE_MAXSIZE=${MM_DATAPREP_PIPELINE_COMPLETION_QUEUE_MAXSIZE:-1}
export MM_DATAPREP_DETECTION_WORKER_THREADS=${MM_DATAPREP_DETECTION_WORKER_THREADS:-2}
export MM_DATAPREP_EMBED_WORKER_THREADS=${MM_DATAPREP_EMBED_WORKER_THREADS:-2}
export MM_DATAPREP_PIPELINE_QUEUE_GET_TIMEOUT_S=${MM_DATAPREP_PIPELINE_QUEUE_GET_TIMEOUT_S:-1.0}
export SAVE_RUNTIME_PIPELINE_STATS=${SAVE_RUNTIME_PIPELINE_STATS:-false}
export MM_DATAPREP_ENABLE_TRACING=${MM_DATAPREP_ENABLE_TRACING:-false}
export VIDEO_FRAME_DECODER_WORKERS=${VIDEO_FRAME_DECODER_WORKERS:-2}
export VIDEO_FRAME_LOG_LEVEL=${VIDEO_FRAME_LOG_LEVEL:-INFO}

# Env vars for multimodal-embedding-serving -------------------------
export EMBEDDING_SERVER_PORT=9777
export EMBEDDING_MODEL_NAME=${EMBEDDING_MODEL_NAME}  # Must be explicitly provided - no default
export EMBEDDING_USE_OV=${EMBEDDING_USE_OV:-$MM_DATAPREP_USE_OPENVINO}
export DEFAULT_START_OFFSET_SEC=${DEFAULT_START_OFFSET_SEC:-0}
export DEFAULT_CLIP_DURATION=${DEFAULT_CLIP_DURATION:--1}
export DEFAULT_NUM_FRAMES=${DEFAULT_NUM_FRAMES:-64}

# Multimodal Embedding API endpoint
export MULTIMODAL_EMBEDDING_ENDPOINT=${MULTIMODAL_EMBEDDING_ENDPOINT:-"http://multimodal-embedding-serving:8000/embeddings"}
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

# Model path configuration
# Note: All OpenVINO models use the same directory for consistency

# Create docker volumes if not exist
if ! docker volume ls | grep -q "${YOLOX_MODELS_VOLUME_NAME}"; then
    echo "Creating Docker volume for YOLOX models: ${YOLOX_MODELS_VOLUME_NAME}"
    docker volume create "${YOLOX_MODELS_VOLUME_NAME}"
fi
if ! docker volume ls | grep -q "ov-models"; then
    echo "Creating Docker volume for ov-models"
    docker volume create ov-models
fi
if ! docker volume ls | grep -q "data-prep"; then
    echo "Creating Docker volume for data-prep"
    docker volume create data-prep
fi

echo -e "${GREEN}Environment variables set for Multimodal DataPrep and Multimodal Embedding Microservice.${NC}"

echo -e "${BLUE}Current Configuration:${NC}"
echo -e "   Registry: ${YELLOW}${REGISTRY}${NC}"
echo -e "   Model: ${YELLOW}${EMBEDDING_MODEL_NAME}${NC}"

# Device configuration is independent per component (no baseline device).
echo -e "   Embedding Device (MM_EMBEDDING_DEVICE): ${YELLOW}${MM_EMBEDDING_DEVICE}${NC}"
echo -e "   Detection Device (MM_DATAPREP_DETECTION_DEVICE): ${YELLOW}${MM_DATAPREP_DETECTION_DEVICE}${NC}"
echo -e "   MME Embedding Device (EMBEDDING_DEVICE): ${YELLOW}${EMBEDDING_DEVICE}${NC}"
echo -e "   OpenVINO: ${YELLOW}${MM_DATAPREP_USE_OPENVINO}${NC}"
echo -e "   OpenVINO Performance Mode: ${YELLOW}${MM_OV_PERFORMANCE_MODE}${NC}"
echo -e "   DataPrep Log Level: ${YELLOW}${MM_DATAPREP_LOG_LEVEL}${NC}"

echo -e "${BLUE}Usage Tips:${NC}"
echo -e "   • To offload DataPrep embedding to GPU: ${YELLOW}export MM_EMBEDDING_DEVICE=GPU${NC} (requires Intel GPU)"
echo -e "   • To offload DataPrep detection to GPU: ${YELLOW}export MM_DATAPREP_DETECTION_DEVICE=GPU${NC}"
echo -e "   • To offload the MME embedding service to GPU: ${YELLOW}export EMBEDDING_DEVICE=GPU${NC}"
echo -e "   • For OpenVINO optimization: ${YELLOW}export MM_DATAPREP_USE_OPENVINO=true${NC} (default)"
echo -e "   • To set DataPrep log level: ${YELLOW}export MM_DATAPREP_LOG_LEVEL=DEBUG${NC}"

echo -e "${BLUE} Quick Device Setup:${NC}"
echo -e "   • ${YELLOW}source ./setup-with-embedding.sh${NC} - Default CPU with OpenVINO"
echo -e "   • ${YELLOW}MM_EMBEDDING_DEVICE=GPU source ./setup-with-embedding.sh${NC} - GPU embedding with validation"
