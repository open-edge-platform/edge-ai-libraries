#!/bin/bash
# Build script for microservice dependencies and sample application backend/UI

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
NC='\033[0m' # No Color

export REGISTRY_URL=${REGISTRY_URL:-}
export PROJECT_NAME=${PROJECT_NAME:-}
export TAG=${TAG:-latest}

[[ -n "$REGISTRY_URL" ]] && REGISTRY_URL="${REGISTRY_URL%/}/"
[[ -n "$PROJECT_NAME" ]] && PROJECT_NAME="${PROJECT_NAME%/}/"
REGISTRY="${REGISTRY_URL}${PROJECT_NAME}"

# Display info about the registry being used
if [ -z "$REGISTRY" ]; then
  echo -e "${YELLOW}Warning: No registry prefix set. Images will be tagged without a registry prefix.${NC}"
  echo "Using local image names with tag: ${TAG}"
else
  echo "Using registry prefix: ${REGISTRY}"
fi

# Usage information
show_usage() {
  echo -e "Usage: $0 [OPTION]"
  echo -e "  --sample-app\t Build sample application services (pipeline-manager, search-ms, and UI)"
  echo -e "  --push\t Push all built Docker images to the registry"
  echo -e "  <no option>\t Build all microservice dependencies"
}

# Logging functions
log_info() {
  local message="$1"
  echo -e "$(date '+%Y-%m-%d %H:%M:%S') - $message" | tee -a "${LOG_FILE:-/dev/null}"
}

# ================================================================================
# Build microservice dependencies
# ================================================================================
build_dependencies() {
  log_info "Building microservice dependencies..."
  
  # Save current directory
  local current_dir=$(pwd)
  local uservices_dir="${current_dir}/../../microservices"
  local build_success=true

  # Build DATAPREP
  cd "${uservices_dir}/document-ingestion/vdms/docker" || return 0
  if [ -f "compose.yaml" ]; then
   cd .. && source setup.sh --build || { 
      log_info "${RED}Failed to build DATAPREP${NC}"; 
      build_success=false; 
    }
  fi
# Check if the directory exists first
if [ -d "${uservices_dir}/multimodal-embedding-serving" ]; then
  cd "${uservices_dir}/multimodal-embedding-serving" || {
    log_info "${RED}Multimodal embedding directory not found${NC}";
    build_success=false;
  }
  if [ -f "compose.yaml" ]; then
    source setup.sh && docker compose build || { 
      log_info "${RED}Failed to build multimodal embedding${NC}"; 
      build_success=false; 
    }
  else
    log_info "${YELLOW}compose.yml not found for multimodal embedding${NC}";
  fi
fi
  
  # Build vlm-ov-serving
  cd "${uservices_dir}/vlm-ov-serving" || return 0
  if [ -f "compose.yaml" ]; then
    source setup.sh && docker compose build || { 
      log_info "${RED}Failed to build vlm-ov-serving${NC}"; 
      build_success=false; 
    }
  fi


  # Build audio intelligence microservice
  cd "${uservices_dir}/audio-intelligence/docker" || return 1
  if [ -f "docker-compose.yaml" ]; then
    cd ../
    ./setup_docker.sh --build || { 
      log_info "${RED}Failed to build audio-intelligence microservice${NC}"; 
      build_success=false; 
    }
  fi


  # Build VLM GPU ov serving
  cd "${uservices_dir}/vlm-ov-serving" || return 0
  if [ -f "compose.gpu.yaml" ]; then
    source setup.sh && docker compose -f compose.gpu.yaml build || { 
      log_info "${RED}Failed to build GPU vlm-ov-serving${NC}"; 
      build_success=false; 
    }
  fi

  # Build video ingestion microservice
  cd "${uservices_dir}/video-ingestion/docker" || return 0
  if [ -f "compose.yaml" ]; then
    docker compose build || { 
      log_info "${RED}Failed to build video-ingestion microservice${NC}"; 
      build_success=false; 
    }
  fi

  # Return to original directory
  cd "$current_dir"
  
  if [ "$build_success" = true ]; then
    log_info "${GREEN}All dependencies built successfully${NC}"
    
    # Print built images
    log_info "${GREEN}Built images:${NC}"
    echo "Retrieving Docker images related to microservice dependencies..."
    docker images | grep -E "${REGISTRY}.*(vdms|multimodal|vlm|audio|video).*${TAG}"
    
    return 0
  else
    log_info "${YELLOW}Some dependencies failed to build. Check logs for details.${NC}"
    return 1
  fi
}

# ================================================================================
# Build sample application Backend and UI
# ================================================================================
build_sample_app() {
  log_info "Building sample application services..."
  
  # Save current directory
  local current_dir=$(pwd)
  local build_success=true

  # Build pipeline-manager backend service
  cd "${current_dir}/pipeline-manager" || return 0
  if [ -f "Dockerfile" ]; then
    log_info "Building pipeline-manager service..."
    docker build -t "${REGISTRY}pipeline-manager:${TAG}" . || { 
      log_info "${RED}Failed to build pipeline-manager service${NC}"; 
      build_success=false; 
    }
  else
    log_info "${YELLOW}Dockerfile not found for pipeline-manager service${NC}";
  fi

  # Build video search backend service
  cd "${current_dir}/search-ms" || return 0
  if [ -f "docker/Dockerfile" ]; then
    log_info "Building search-ms service..."
    docker build -t "${REGISTRY}video-search:${TAG}" -f docker/Dockerfile . || { 
      log_info "${RED}Failed to build search-ms service${NC}"; 
      build_success=false; 
    }
  else
    log_info "${YELLOW}Dockerfile not found for search-ms service${NC}";
  fi

  # Build UI service
  cd "${current_dir}/ui/react" || return 0
  if [ -f "Dockerfile" ]; then
    log_info "Building UI service..."
    docker build -t "${REGISTRY}vss-ui:${TAG}" . || { 
      log_info "${RED}Failed to build UI service${NC}"; 
      build_success=false; 
    }
  else
    log_info "${YELLOW}Dockerfile not found for UI service${NC}";
  fi

  # Return to original directory
  cd "$current_dir"
  
  if [ "$build_success" = true ]; then
    log_info "${GREEN}All sample application services built successfully${NC}"
    
    # Print built images
    log_info "${GREEN}Built sample application images:${NC}"
    echo "Retrieving Docker images related to sample applications..."
    docker images | grep -E "${REGISTRY}.*(vss-ui|video-search|pipeline-manager).*$TAG"
    
    return 0
  else
    log_info "${YELLOW}Some sample application services failed to build. Check logs for details.${NC}"
    return 1
  fi
}

# ================================================================================
# Push all built Docker images to the registry
# ================================================================================
push_images() {
  log_info "Pushing Docker images to registry..."
  
  # Save current directory
  local current_dir=$(pwd)
  local push_success=true

  # Get list of dependency images to push
  log_info "Pushing dependency images..."
  dependency_images=$(docker images | grep -E "${REGISTRY}.*(vdms|multimodal|vlm|audio).*${TAG}" | awk '{print $1":"$2}')
  
  # Push dependency images
  for image in $dependency_images; do
    log_info "Pushing $image..."
    docker push $image || {
      log_info "${RED}Failed to push $image${NC}";
      push_success=false;
    }
  done

  # Push sample application images
  log_info "Pushing sample application images..."
  app_images=$(docker images | grep -E "${REGISTRY}.*(pipeline-manager|video-search|vss-ui).*${TAG}" | awk '{print $1":"$2}')
  
  for image in $app_images; do
    log_info "Pushing $image..."
    docker push $image || {
      log_info "${RED}Failed to push $image${NC}";
      push_success=false;
    }
  done

  if [ "$push_success" = true ]; then
    log_info "${GREEN}All images pushed successfully${NC}"
    return 0
  else
    log_info "${YELLOW}Some images failed to push. Check logs for details.${NC}"
    return 1
  fi
}

# ================================================================================

# Parse command line arguments
if [ "$1" == "--help" ] || [ "$1" == "-h" ]; then
  show_usage
elif [ "$1" == "--sample-app" ]; then
  build_sample_app
elif [ "$1" == "--push" ]; then
  push_images
else
  build_dependencies
fi