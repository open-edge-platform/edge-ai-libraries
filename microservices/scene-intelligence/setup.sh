#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Color codes for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Setting variables for directories used as volume mounts
SOURCE="src"
SECRETS_DIR="${SOURCE}/secrets"

# Setting command usage and invalid arguments handling before the actual setup starts
if [ "$#" -eq 0 ] || ([ "$#" -eq 1 ] && [ "$1" = "--help" ]); then
    # If no valid argument is passed, print usage information
    echo -e "-----------------------------------------------------------------"
    echo -e "${YELLOW}USAGE: ${GREEN}source setup.sh ${BLUE}[--setenv | --secrets | --videos | --build | --run | --stop | --clean | --status | --help | --setup]"
    echo -e "${YELLOW}"
    echo -e "  --setenv:     Set environment variables without starting any containers"
    echo -e "  --secrets:    Generate secrets only"
    echo -e "  --videos:     Download demo videos only"
    echo -e "  --build:      Download videos and build Docker images"
    echo -e "  --run:        Start the service and AI Route Planner"
    echo -e "  --stop:       Stop the service and AI Route Planner"
    echo -e "  --clean:      Clean up containers, volumes, and AI Route Planner logs"
    echo -e "  --status:     Show service status including AI Route Planner"
    echo -e "  --setup:      Full setup: secrets + videos + build + run (includes AI Route Planner)"
    echo -e "  --help:       Show this help message${NC}"
    echo -e "-----------------------------------------------------------------"
    return 0

elif [ "$#" -gt 1 ]; then
    echo -e "${RED}ERROR: Too many arguments provided.${NC}"
    echo -e "${YELLOW}Use --help for usage information${NC}"
    return 1

elif [ "$1" != "--help" ] && [ "$1" != "--setenv" ] && [ "$1" != "--secrets" ] && [ "$1" != "--videos" ] && [ "$1" != "--build" ] && [ "$1" != "--run" ] && [ "$1" != "--stop" ] && [ "$1" != "--clean" ] && [ "$1" != "--status" ] && [ "$1" != "--setup" ]; then
    # Default case for unrecognized option
    echo -e "${RED}Unknown option: $1 ${NC}"
    echo -e "${YELLOW}Use --help for usage information${NC}"
    return 1

elif [ "$1" = "--stop" ]; then
    # If --stop is passed, bring down the Docker containers and stop AI Route Planner
    echo -e "${YELLOW}Stopping Scene Intelligence service... ${NC}"
    
    # Stop AI Route Planner first
    stop_ai_route_planner
    
    # Stop Docker services
    docker compose -f docker/compose.yaml down
    if [ $? -ne 0 ]; then
        return 1
    fi
    echo -e "${GREEN}Scene Intelligence service stopped successfully. ${NC}"
    return 0

elif [ "$1" = "--clean" ]; then
    # If --clean is passed, clean up containers and volumes
    echo -e "${YELLOW}Cleaning up containers and volumes... ${NC}"
    
    # Stop AI Route Planner first
    stop_ai_route_planner
    
    # Clean up log files
    rm -f ai-route-planner.log
    
    docker compose -f docker/compose.yaml down --rmi all --volumes --remove-orphans
    if [ $? -ne 0 ]; then
        return 1
    fi
    echo -e "${GREEN}Cleanup completed successfully. ${NC}"
    return 0

elif [ "$1" = "--status" ]; then
    # Show service status
    echo -e "${BLUE}Scene Intelligence Service Status:${NC}"
    docker compose -f docker/compose.yaml ps
    
    echo ""
    echo -e "${BLUE}AI Route Planner Status:${NC}"
    if lsof -i :${AI_ROUTE_PLANNER_PORT} > /dev/null 2>&1; then
        echo -e "${GREEN}✓ AI Route Planner is running on port ${AI_ROUTE_PLANNER_PORT}${NC}"
        echo -e "  URL: ${YELLOW}http://localhost:${AI_ROUTE_PLANNER_PORT}${NC}"
    else
        echo -e "${RED}✗ AI Route Planner is not running${NC}"
    fi
    return 0
fi

# Export all environment variables
# Base configuration
export HOST_IP=$(ip route get 1 | awk '{print $7}')  # Fetch the host IP
# Add HOST_IP to no_proxy only if not already present
[[ $no_proxy != *"${HOST_IP}"* ]] && export no_proxy="${no_proxy},${HOST_IP}"
export TAG=${TAG:-latest}
export REGISTRY_URL=${REGISTRY_URL:-amr-fm-registry.caas.intel.com/esh-user/}
export PROJECT_NAME=${PROJECT_NAME:-egai/}

# If REGISTRY_URL is set, ensure it ends with a trailing slash
# Using parameter expansion to conditionally append '/' if not already present
[[ -n "$REGISTRY_URL" ]] && REGISTRY_URL="${REGISTRY_URL%/}/"

# If PROJECT_NAME is set, ensure it ends with a trailing slash
[[ -n "$PROJECT_NAME" ]] && PROJECT_NAME="${PROJECT_NAME%/}/"

export REGISTRY="${REGISTRY_URL}${PROJECT_NAME}"
echo -e "${GREEN}Using registry: ${YELLOW}$REGISTRY ${NC}"

# Scene Intelligence Service Configuration
export MQTT_PORT=${MQTT_PORT:-1883}
export SCENESCAPE_PORT=${SCENESCAPE_PORT:-443}
export SCENE_INTELLIGENCE_PORT=${SCENE_INTELLIGENCE_PORT:-8082}
export DLSTREAMER_PORT=${DLSTREAMER_PORT:-8555}

# User and group IDs
export USER_ID=$(id -u)
export USER_GROUP_ID=$(id -g)
export UID=${UID:-$(id -u)}
export GID=${GID:-$(id -g)}

# SceneScape Database Configuration
export DBROOT=${DBROOT:-/workspace}
export EXAMPLEDB=${EXAMPLEDB:-scene-intelligence.tar.bz2}

# Traffic Analysis Configuration
export TRAFFIC_BUFFER_DURATION=${TRAFFIC_BUFFER_DURATION:-60}
export LOG_LEVEL=${LOG_LEVEL:-INFO}
export DATA_RETENTION_HOURS=${DATA_RETENTION_HOURS:-24}

# SceneScape Configuration
export SCENESCAPE_URL=${SCENESCAPE_URL:-https://web.scenescape.intel.com}
export MQTT_BROKER_HOST=${MQTT_BROKER_HOST:-broker.scenescape.intel.com}
export MQTT_BROKER_PORT=${MQTT_BROKER_PORT:-1883}

# Proxy settings
export no_proxy_env=${no_proxy}

# Scene Intelligence Service Configuration
export SCENE_INTELLIGENCE_CONFIG=${SCENE_INTELLIGENCE_CONFIG:-/app/config/scene_intelligence_config.json}

# Health Check Configuration
export HEALTH_CHECK_INTERVAL=${HEALTH_CHECK_INTERVAL:-30s}
export HEALTH_CHECK_TIMEOUT=${HEALTH_CHECK_TIMEOUT:-10s}
export HEALTH_CHECK_RETRIES=${HEALTH_CHECK_RETRIES:-3}
export HEALTH_CHECK_START_PERIOD=${HEALTH_CHECK_START_PERIOD:-10s}

# VLM Service Configuration
export VLM_SERVICE_PORT=${VLM_SERVICE_PORT:-9764}
export VLM_BASE_URL=${VLM_BASE_URL:-http://vlm-openvino-serving:8000}
export VLM_MODEL=${VLM_MODEL:-Qwen/Qwen2.5-VL-3B-Instruct}
export VLM_MODEL_NAME=${VLM_MODEL_NAME:-Qwen/Qwen2.5-VL-3B-Instruct}
export HIGH_DENSITY_THRESHOLD=${HIGH_DENSITY_THRESHOLD:-5.0}
export MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS=${MINIMUM_DURATION_FOR_CONSISTENTLY_HIGH_TRAFFIC_SECONDS:-2}
export VLM_COOLDOWN_MINUTES=${VLM_COOLDOWN_MINUTES:-1}
export VLM_TIMEOUT_SECONDS=${VLM_TIMEOUT_SECONDS:-300}
export VLM_MAX_COMPLETION_TOKENS=${VLM_MAX_COMPLETION_TOKENS:-500}
export VLM_TEMPERATURE=${VLM_TEMPERATURE:-0.3}
export VLM_TOP_P=${VLM_TOP_P:-0.9}
export VLM_CONFIG_FILE=${VLM_CONFIG_FILE:-config/vlm_config.json}

# AI Route Planner Configuration
export AI_ROUTE_PLANNER_PORT=${AI_ROUTE_PLANNER_PORT:-7864}
export AI_ROUTE_PLANNER_DIR=${AI_ROUTE_PLANNER_DIR:-ai-route-planner}

# VLM Prompts (optional environment variable overrides)
# export VLM_SYSTEM_PROMPT="Custom system prompt..."
# export VLM_TRAFFIC_ANALYSIS_PROMPT="Custom traffic analysis prompt with {intersection_id}, {directions_text}, {density_info}, {high_density_threshold} placeholders..."

# VLM OpenVINO Configuration (for VLM microservice)
export VLM_DEVICE=${VLM_DEVICE:-CPU}
export VLM_COMPRESSION_WEIGHT_FORMAT=${VLM_COMPRESSION_WEIGHT_FORMAT:-int8}
export VLM_SEED=${VLM_SEED:-42}
export VLM_WORKERS=${VLM_WORKERS:-4}  # Set to 4 for concurrent intersection analysis
export VLM_LOG_LEVEL=${VLM_LOG_LEVEL:-info}
export VLM_ACCESS_LOG_FILE=${VLM_ACCESS_LOG_FILE:-/dev/null}

# Automatically adjust VLM settings for GPU
if [[ "$VLM_DEVICE" == "GPU" ]]; then
    export VLM_COMPRESSION_WEIGHT_FORMAT=int4
    export VLM_WORKERS=1  # GPU works best with single worker
fi

# Export current user and group IDs for VLM container
export VIDEO_GROUP_ID=$(getent group video | awk -F: '{printf "%s\n", $3}' 2>/dev/null || echo "44")
export RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}' 2>/dev/null || echo "109")

echo -e "${GREEN}Environment variables set:${NC}"
echo -e "  HOST_IP: ${YELLOW}$HOST_IP${NC}"
echo -e "  TAG: ${YELLOW}$TAG${NC}"
echo -e "  REGISTRY: ${YELLOW}$REGISTRY${NC}"
echo -e "  MQTT_PORT: ${YELLOW}$MQTT_PORT${NC}"
echo -e "  SCENESCAPE_PORT: ${YELLOW}$SCENESCAPE_PORT${NC}"
echo -e "  SCENE_INTELLIGENCE_PORT: ${YELLOW}$SCENE_INTELLIGENCE_PORT${NC}"
echo -e "  VLM_SERVICE_PORT: ${YELLOW}$VLM_SERVICE_PORT${NC}"
echo -e "  AI_ROUTE_PLANNER_PORT: ${YELLOW}$AI_ROUTE_PLANNER_PORT${NC}"
echo -e "  VLM_MODEL_NAME: ${YELLOW}$VLM_MODEL_NAME${NC}"
echo -e "  VLM_WORKERS: ${YELLOW}$VLM_WORKERS${NC}"
echo -e "  VLM_DEVICE: ${YELLOW}$VLM_DEVICE${NC}"
echo -e "  HIGH_DENSITY_THRESHOLD: ${YELLOW}$HIGH_DENSITY_THRESHOLD${NC}"
echo -e "  VLM_COOLDOWN_MINUTES: ${YELLOW}$VLM_COOLDOWN_MINUTES${NC}"
echo -e "  UID: ${YELLOW}$UID${NC}"
echo -e "  GID: ${YELLOW}$GID${NC}"

# Function to generate secrets
generate_secrets() {
    echo -e "${BLUE}==> Generating secrets...${NC}"
    
    if [ ! -f "${SECRETS_DIR}/generate_secrets.sh" ]; then
        echo -e "${RED}Error: ${SECRETS_DIR}/generate_secrets.sh not found!${NC}"
        return 1
    fi
    
    # Generate secrets if they don't exist
    if [ ! -f "${SECRETS_DIR}/browser.auth" ]; then
        echo -e "${YELLOW}Generating new secrets...${NC}"
        bash "${SECRETS_DIR}/generate_secrets.sh"
        echo -e "${GREEN}Secrets generated successfully${NC}"
    else
        echo -e "${YELLOW}Secrets already exist, skipping generation${NC}"
        echo -e "${YELLOW}To force regeneration, delete ${SECRETS_DIR} and run again${NC}"
    fi
}

# Function to download demo videos
download_videos() {
    echo -e "${BLUE}==> Downloading demo videos...${NC}"
    
    VIDEO_DIR="${SOURCE}/dlstreamer-pipeline-server/videos"
    
    # Check if videos already exist
    if [ -d "${VIDEO_DIR}" ] && [ -n "$(find "${VIDEO_DIR}" -type f -name "*.ts" 2>/dev/null)" ]; then
        echo -e "${YELLOW}Videos already exist, skipping download${NC}"
        echo -e "${GREEN}Found existing videos:${NC}"
        ls -la "${VIDEO_DIR}"/*.ts 2>/dev/null | awk '{print "  " $9 " (" $5 " bytes)"}'
        return 0
    fi
    
    # Create video directory
    mkdir -p "${VIDEO_DIR}"
    
    # Video download configuration
    VIDEO_URL="https://github.com/intel/metro-ai-suite/raw/refs/heads/videos/videos"
    VIDEOS=("1122east.ts" "1122west.ts" "1122north.ts" "1122south.ts")
    
    echo -e "${YELLOW}Downloading videos from: ${VIDEO_URL}${NC}"
    
    # Download each video
    for VIDEO in "${VIDEOS[@]}"; do
        echo -e "${YELLOW}Downloading ${VIDEO}...${NC}"
        
        if curl -L --fail --progress-bar "${VIDEO_URL}/${VIDEO}" -o "${VIDEO_DIR}/${VIDEO}"; then
            echo -e "${GREEN}✓ Downloaded ${VIDEO} successfully${NC}"
        else
            echo -e "${RED}✗ Error: Failed to download ${VIDEO}${NC}"
            echo -e "${RED}Please check your internet connection and try again${NC}"
            return 1
        fi
    done
    
    echo -e "${GREEN}All videos downloaded successfully!${NC}"
    echo -e "${BLUE}Downloaded videos:${NC}"
    ls -la "${VIDEO_DIR}"/*.ts 2>/dev/null | awk '{print "  " $9 " (" $5 " bytes)"}'
}

# Function to build Docker images
build_images() {
    echo -e "${BLUE}==> Building Docker images...${NC}"
    
    docker compose -f docker/compose.yaml build
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Docker images built successfully${NC}"
    else
        echo -e "${RED}Failed to build Docker images${NC}"
        return 1
    fi
}

# Function to stop AI Route Planner
stop_ai_route_planner() {
    echo -e "${YELLOW}Stopping AI Route Planner...${NC}"
    
    if lsof -i :${AI_ROUTE_PLANNER_PORT} > /dev/null 2>&1; then
        echo -e "${YELLOW}Found AI Route Planner running on port ${AI_ROUTE_PLANNER_PORT}, stopping...${NC}"
        fuser -k ${AI_ROUTE_PLANNER_PORT}/tcp 2>/dev/null
        sleep 1
        
        # Verify it's stopped
        if lsof -i :${AI_ROUTE_PLANNER_PORT} > /dev/null 2>&1; then
            echo -e "${RED}Failed to stop AI Route Planner${NC}"
        else
            echo -e "${GREEN}AI Route Planner stopped successfully${NC}"
        fi
    else
        echo -e "${YELLOW}AI Route Planner is not running${NC}"
    fi
}

# Function to start AI Route Planner
start_ai_route_planner() {
    echo -e "${BLUE}==> Starting AI Route Planner...${NC}"
    
    # Check if the AI Route Planner directory exists
    if [ ! -d "${AI_ROUTE_PLANNER_DIR}" ]; then
        echo -e "${YELLOW}AI Route Planner directory '${AI_ROUTE_PLANNER_DIR}' not found, skipping...${NC}"
        return 0
    fi
    
    # Check if uv is installed
    if ! command -v uv &> /dev/null; then
        echo -e "${YELLOW}uv is not installed. AI Route Planner requires uv to run.${NC}"
        echo -e "${YELLOW}Please install uv first: https://docs.astral.sh/uv/getting-started/installation/${NC}"
        return 0
    fi
    
    # Check if port is already in use
    if lsof -i :${AI_ROUTE_PLANNER_PORT} > /dev/null 2>&1; then
        echo -e "${YELLOW}Port ${AI_ROUTE_PLANNER_PORT} is already in use. Stopping existing process...${NC}"
        fuser -k ${AI_ROUTE_PLANNER_PORT}/tcp 2>/dev/null
        sleep 2
    fi
    
    # Change to AI Route Planner directory and start the application in background
    (
        cd "${AI_ROUTE_PLANNER_DIR}"
        echo -e "${YELLOW}Starting AI Route Planner with uv run main.py...${NC}"
        nohup uv run main.py >| ../ai-route-planner.log 2>&1 &
        echo -e "${GREEN}AI Route Planner started in background${NC}"
        echo -e "${YELLOW}Logs available at: ai-route-planner.log${NC}"
    )
    
    # Give it a moment to start
    sleep 3
    
    # Check if it's running by checking the port
    if lsof -i :${AI_ROUTE_PLANNER_PORT} > /dev/null 2>&1; then
        echo -e "${GREEN}✓ AI Route Planner is running on port ${AI_ROUTE_PLANNER_PORT}${NC}"
    else
        echo -e "${YELLOW}AI Route Planner may have failed to start. Check ai-route-planner.log for details.${NC}"
    fi
}

# Function to start the service
start_service() {
    echo -e "${BLUE}==> Starting Scene Intelligence service...${NC}"
    
    # Check prerequisites
    if [ ! -f "${SECRETS_DIR}/browser.auth" ]; then
        echo -e "${YELLOW}Secrets not found. Generating them first...${NC}"
        generate_secrets
        if [ $? -ne 0 ]; then
            return 1
        fi
    fi
    
    # Start the service
    docker compose -f docker/compose.yaml up -d
    
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}Scene Intelligence service started successfully!${NC}"
        
        # Start AI Route Planner
        start_ai_route_planner
        
        echo ""
        echo -e "${BLUE}Services:${NC}"
        echo -e "  • Scene Intelligence API: ${YELLOW}http://localhost:${SCENE_INTELLIGENCE_PORT}${NC}"
        echo -e "  • AI Route Planner: ${YELLOW}http://localhost:${AI_ROUTE_PLANNER_PORT}${NC}"
        echo -e "  • SceneScape Web: ${YELLOW}https://localhost:${SCENESCAPE_PORT}${NC}"
        echo -e "  • MQTT Broker: ${YELLOW}localhost:${MQTT_PORT}${NC}"
        echo -e "  • DL Streamer: ${YELLOW}http://localhost:${DLSTREAMER_PORT}${NC}"
        echo ""
        echo -e "${BLUE}API Endpoints:${NC}"
        echo -e "  • Health Check: ${YELLOW}http://localhost:${SCENE_INTELLIGENCE_PORT}/health${NC}"
        echo -e "  • Traffic Summary: ${YELLOW}http://localhost:${SCENE_INTELLIGENCE_PORT}/api/v1/traffic/summary${NC}"
        echo -e "  • Traffic Intersections: ${YELLOW}http://localhost:${SCENE_INTELLIGENCE_PORT}/api/v1/traffic/intersections${NC}"
        echo ""
        echo -e "${BLUE}To view logs:${NC}"
        echo -e "  ${YELLOW}docker compose -f docker/compose.yaml logs -f${NC}"
        echo ""
        echo -e "${BLUE}To stop the service:${NC}"
        echo -e "  ${YELLOW}source setup.sh --stop${NC}"
    else
        echo -e "${RED}Failed to start Scene Intelligence service${NC}"
        return 1
    fi
}

# Verify if required directories exist
if [ "$1" != "--setenv" ] && [ "$1" != "--stop" ] && [ "$1" != "--clean" ] && [ "$1" != "--status" ]; then
    if [ ! -d "${SOURCE}" ]; then
        echo -e "${RED}Error: Source directory '${SOURCE}' not found${NC}"
        return 1
    fi
    
    if [ ! -d "${SECRETS_DIR}" ]; then
        echo -e "${YELLOW}Warning: Secrets directory '${SECRETS_DIR}' not found${NC}"
        echo -e "${YELLOW}Secrets will be generated when needed${NC}"
    fi
fi

# if only base environment variables are to be set without deploying application, exit here
if [ "$1" = "--setenv" ]; then
    echo -e "${BLUE}Done setting up all environment variables. ${NC}"
    return 0
fi

# Main logic based on command
case $1 in
    --secrets)
        generate_secrets
        ;;
    --videos)
        download_videos
        ;;
    --build)
        download_videos
        if [ $? -eq 0 ]; then
            build_images
        fi
        ;;
    --run)
        start_service
        ;;
    --setup|*)
        echo -e "${BLUE}==> Full Scene Intelligence Setup${NC}"
        generate_secrets
        if [ $? -eq 0 ]; then
            download_videos
            if [ $? -eq 0 ]; then
                build_images
                if [ $? -eq 0 ]; then
                    start_service
                fi
            fi
        fi
        ;;
esac

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Done!${NC}"
else
    echo -e "${RED}Setup failed. Check the logs above for details.${NC}"
    return 1
fi
