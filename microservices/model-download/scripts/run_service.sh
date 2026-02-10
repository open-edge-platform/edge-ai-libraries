#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Color definitions
NC='\033[0m'          # No Color
GREEN='\033[0;32m'    # Green
YELLOW='\033[1;33m'   # Yellow
BLUE='\033[0;34m'     # Blue
RED='\033[0;31m'      # Red
CYAN='\033[0;36m'     # Cyan
BOLD='\033[1m'        # Bold

# Default values
DEFAULT_MODEL_PATH="$HOME/models/"
BUILD=false
BUILD_ONLY=false
REBUILD=false
PLUGINS=""
MODEL_PATH=""
ACTION="up"

# Function to log messages with color
log_info() {
    echo -e "${BLUE}INFO:${NC} $1"
}

log_success() {
    echo -e "${GREEN}SUCCESS:${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}WARNING:${NC} $1"
}

log_error() {
    echo -e "${RED}ERROR:${NC} $1"
}

# Function to display script usage
show_usage() {
    echo -e "${BOLD}Usage:${NC}source scripts/run_service.sh [options] [action]"
    echo -e "${BOLD}Actions:${NC}"
    echo -e "  ${CYAN}up${NC}                     Start the services (default)"
    echo -e "  ${CYAN}down${NC}                   Stop the services"
    echo -e "${BOLD}Options:${NC}"
    echo -e "  ${CYAN}--build${NC}                Build the Docker image only (without starting services)"
    echo -e "  ${CYAN}--rebuild${NC}              Force rebuild the Docker image without cache (without starting services)"
    echo -e "  ${CYAN}--model-path${NC} <path>    Set custom model path (default: $DEFAULT_MODEL_PATH)"
    echo -e "  ${CYAN}--plugins${NC} <list>       Comma-separated list of plugins to enable (e.g., huggingface,ollama,ultralytics,geti) or 'all' to enable all"
    echo -e "  ${CYAN}--help${NC}                 Show this help message"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        up)
            ACTION="up"
            shift
            ;;
        down)
            ACTION="down"
            shift
            ;;
        --build)
            BUILD=true
            BUILD_ONLY=true
            shift
            ;;
        --rebuild)
            REBUILD=true
            BUILD=true
            BUILD_ONLY=true
            shift
            ;;
        --model-path)
            if [[ -n "$2" && "$2" != --* ]]; then
                MODEL_PATH="$2"
                shift 2
            else
                log_error "--model-path requires a path argument"
                return 1
            fi
            ;;
        --plugins)
            if [[ -n "$2" && "$2" != --* ]]; then
                PLUGINS="$2"
                shift 2
            else
                log_error "--plugins requires a comma-separated list"
                return 1
            fi
            ;;
        --help)
            show_usage
            return 0
            ;;
        *)
            log_error "Unknown option or action: $1"
            show_usage
            return 1
            ;;
    esac
done

# Skip model path setup and other operations for "down" action
if [[ "$ACTION" != "down" ]]; then
    # If model path is not provided, use default
    if [[ -z "$MODEL_PATH" ]]; then
        MODEL_PATH="$DEFAULT_MODEL_PATH"
    fi
    
    log_info "Setting up model path: ${BOLD}$MODEL_PATH${NC}"

    if [[ "$MODEL_PATH" != /* ]]; then
        MODEL_PATH="$PWD/$MODEL_PATH"
        log_info "Relative path provided. Using absolute path: ${BOLD}$MODEL_PATH${NC}"
    fi

    # Check if MODEL_PATH exists
    if [ -e "$MODEL_PATH" ]; then
        # If it exists, check the owner
        if [ "$(stat -c '%U:%G' "$MODEL_PATH")" != "root:root" ]; then
            log_info "${BOLD}$MODEL_PATH${NC} exists in host..."
        else
            # If owned by root:root, delete and recreate it
            log_warning "$MODEL_PATH exists and is owned by root:root. Deleting it and recreate..."
            sudo rm -rf "$MODEL_PATH"
            mkdir -p "$MODEL_PATH"
            log_success "Recreated ${BOLD}$MODEL_PATH${NC} with correct permissions."
        fi
    else
        # If it doesn't exist, create it
        log_info "${BOLD}$MODEL_PATH${NC} does not exist. Creating it..."
        mkdir -p "$MODEL_PATH"
        log_success "Created ${BOLD}$MODEL_PATH${NC} successfully."
    fi

    # Get the current user group ID for Docker permissions
    USER_GROUP_ID=$(id -g)

    # Export environment variables for docker-compose
    if [[ -n "$REGISTRY" && -n "$TAG" ]]; then
        export TAG="$TAG"
        export REGISTRY="$REGISTRY"
    else
        export TAG="latest"
    fi
    export USER_GROUP_ID="$USER_GROUP_ID"
    export MODEL_PATH="$MODEL_PATH"
    export ENABLED_PLUGINS="$PLUGINS"

    # Generate environment file for docker-compose in current directory
    log_info "Generating environment settings..."
    cat > .env << EOF
TAG=$TAG
REGISTRY=$REGISTRY
USER_GROUP_ID=$USER_GROUP_ID
MODEL_PATH=$MODEL_PATH
ENABLED_PLUGINS=$PLUGINS
EOF
    log_success "Environment settings generated successfully."
fi

# Handle the action
case "$ACTION" in
    up)
        # Build the Docker image if requested
        if [[ "$BUILD" == true ]]; then
            BUILD_COMMAND="docker compose -f docker/compose.yaml build"
            
            # Add no-cache option if rebuild is requested
            if [[ "$REBUILD" == true ]]; then
                BUILD_COMMAND="$BUILD_COMMAND --no-cache"
            fi
            
            log_info "Building Docker image: ${BOLD}$BUILD_COMMAND${NC}"
            eval "$BUILD_COMMAND" || { log_error "Docker build failed"; return 1; }
            log_success "Docker image built successfully."
            
            # If build-only mode, exit here
            if [[ "$BUILD_ONLY" == true ]]; then
                log_success "Build completed. Use 'source scripts/run_service.sh up' to start the service."
                return 0
            fi
        fi

        # Run the Docker container
        log_info "Starting model download service..."
        if docker compose ps | grep -q "model_download"; then
            log_warning "Service is already running. Stopping first..."
            docker compose -f docker/compose.yaml down
        fi

        docker compose -f docker/compose.yaml up

        ;;
    down)
        # For down action, we only need to stop the services
        log_info "Stopping model download service..."
        docker compose -f docker/compose.yaml down
        log_success "Model download service stopped."
        ;;
    *)
        log_error "Unknown action: $ACTION"
        show_usage
        return 1
        ;;
esac