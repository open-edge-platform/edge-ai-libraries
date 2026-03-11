#!/bin/bash

# Combined setup for VDMS DataPrep and Multimodal Embedding Microservice
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
export COVERAGE_REQ=80
export PROJ_TEST_DIR=./tests
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

# Env vars for vdms-dataprep -----------------------------------------
export INDEX_NAME="video-rag"
export DEFAULT_BUCKET_NAME="vdms-bucket"
export VDMS_DATAPREP_HOST_PORT=6007
export YOLOX_MODELS_VOLUME_NAME="vdms-yolox-models"
export YOLOX_MODELS_MOUNT_PATH="/app/models/yolox"

# Embedding processing mode settings (SDK vs API)
# EMBEDDING_PROCESSING_MODE options:
#   - "sdk": Use multimodal embedding service directly as SDK (optimized approach with better memory usage, default)
#   - "api": Use HTTP API calls to multimodal embedding service (existing approach)
export EMBEDDING_PROCESSING_MODE=${EMBEDDING_PROCESSING_MODE:-"sdk"}
# Note: EMBEDDING_MODEL_NAME is used for model selection in both SDK and API modes
export SDK_USE_OPENVINO=${SDK_USE_OPENVINO:-true}
export VDMS_DATAPREP_DEVICE=${VDMS_DATAPREP_DEVICE:-"CPU"}
export OV_MODELS_DIR=${OV_MODELS_DIR:-"/app/ov_models"}
export EMBEDDING_OV_MODELS_DIR=${EMBEDDING_OV_MODELS_DIR:-$OV_MODELS_DIR}
export OV_PERFORMANCE_MODE=${OV_PERFORMANCE_MODE:-"THROUGHPUT"}

# Device Configuration Helper Functions
configure_device() {
    local device=${1:-"CPU"}
    
    echo -e "${BLUE}Configuring device for all processing components: ${YELLOW}${device}${NC}"
    echo -e "${BLUE}   This affects: decord video processing, embedding model, and object detection${NC}"
    
    if [[ "${device}" == "GPU" ]]; then
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
        export VDMS_DATAPREP_DEVICE="GPU"
        export SDK_USE_OPENVINO=true  # Force OpenVINO for GPU mode
        
        echo -e "${GREEN}GPU mode configured for all components:${NC}"
        echo -e "   • OpenVINO: ${YELLOW}enabled${NC} (required for GPU)"
        echo -e "   • Processing Device: ${YELLOW}GPU${NC} (decord, embedding, detection)"
        echo -e "   • Video decoding: ${YELLOW}GPU-accelerated${NC}"
        
    else
        echo -e "${BLUE} CPU mode configured for all components${NC}"
        export VDMS_DATAPREP_DEVICE="CPU"
    fi
}

# Device mode selection
if [[ "${VDMS_DATAPREP_DEVICE}" == "GPU" ]]; then
    configure_device "GPU"
else
    configure_device "CPU"
fi

# Align EMBEDDING_DEVICE with resolved device for SDK runtime configuration
export EMBEDDING_DEVICE=${EMBEDDING_DEVICE:-$VDMS_DATAPREP_DEVICE}

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
export VDMS_DATAPREP_LOG_LEVEL=${VDMS_DATAPREP_LOG_LEVEL:-INFO}

# Env vars for multimodal-embedding-serving -------------------------
export EMBEDDING_SERVER_PORT=9777
export EMBEDDING_MODEL_NAME=${EMBEDDING_MODEL_NAME}  # Must be explicitly provided - no default
export EMBEDDING_USE_OV=${EMBEDDING_USE_OV:-$SDK_USE_OPENVINO}
export DEFAULT_START_OFFSET_SEC=${DEFAULT_START_OFFSET_SEC:-0}
export DEFAULT_CLIP_DURATION=${DEFAULT_CLIP_DURATION:--1}
export DEFAULT_NUM_FRAMES=${DEFAULT_NUM_FRAMES:-64}

# Multimodal Embedding API endpoint
export MULTIMODAL_EMBEDDING_ENDPOINT=${MULTIMODAL_EMBEDDING_ENDPOINT:-"http://multimodal-embedding-serving:8000/embeddings"}
export USER_ID=$(id -u)
export USER_GROUP_ID=$(id -g)
export VIDEO_GROUP_ID=$(getent group video | awk -F: '{printf "%s\n", $3}')
export RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')

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

echo -e "${GREEN}Environment variables set for VDMS DataPrep and Multimodal Embedding Microservice.${NC}"

echo -e "${BLUE}Current Configuration:${NC}"
echo -e "   Embedding Mode: ${YELLOW}${EMBEDDING_PROCESSING_MODE}${NC}"
echo -e "   Registry: ${YELLOW}${REGISTRY}${NC}"
echo -e "   Model: ${YELLOW}${EMBEDDING_MODEL_NAME}${NC}"
echo -e "   Device: ${YELLOW}${VDMS_DATAPREP_DEVICE}${NC}"
echo -e "   OpenVINO: ${YELLOW}${SDK_USE_OPENVINO}${NC}"
echo -e "   OpenVINO Performance Mode: ${YELLOW}${OV_PERFORMANCE_MODE}${NC}"
echo -e "   DataPrep Log Level: ${YELLOW}${VDMS_DATAPREP_LOG_LEVEL}${NC}"

echo -e "${BLUE}Usage Tips:${NC}"
echo -e "   • To use SDK mode (optimized memory usage, default): ${YELLOW}export EMBEDDING_PROCESSING_MODE=sdk${NC}"
echo -e "   • To use API mode: ${YELLOW}export EMBEDDING_PROCESSING_MODE=api${NC}"
echo -e "   • For GPU acceleration: ${YELLOW}export VDMS_DATAPREP_DEVICE=GPU${NC} (requires Intel GPU)"
echo -e "   • For CPU processing: ${YELLOW}export VDMS_DATAPREP_DEVICE=CPU${NC}"
echo -e "   • For OpenVINO optimization: ${YELLOW}export SDK_USE_OPENVINO=true${NC} (default)"
echo -e "   • To set DataPrep log level: ${YELLOW}export VDMS_DATAPREP_LOG_LEVEL=DEBUG${NC}"

echo -e "${BLUE} Quick Device Setup:${NC}"
echo -e "   • ${YELLOW}./embedding-setup.sh${NC} - Default SDK mode with CPU and OpenVINO"
echo -e "   • ${YELLOW}VDMS_DATAPREP_DEVICE=GPU ./embedding-setup.sh${NC} - SDK mode with GPU acceleration and validation"
