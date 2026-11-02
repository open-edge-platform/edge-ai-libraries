#!/bin/bash
# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

#######################################
# UAV Mission Compute SDK System Resource Checker and Installation Script
# Checks CPU, Memory, Storage, and Intel GPU resources
# Installs Docker, Docker Compose, and required container images
# Globals:
#   None
# Arguments:
#   --skip-system-check: Skip system resource check
#   --skip-docker: Skip Docker installation
#   --skip-images: Skip Docker image download
#   --skip-git-clone: Skip git repository cloning
#   --help: Show help message
# Outputs:
#   System resource information and installation status to stdout
#######################################


# Array of repositories to clone: "url|branch|directory"
repositories=(
  "https://github.com/open-edge-platform/federal-and-aerospace-ai-suite|main|federal-and-aerospace-ai-suite"
)

# Placeholder for Docker images to pull;
images=(
  "influxdb:2.9.1"
  "grafana/grafana:11.4.0"
  "intel/metrics-manager:2026.1.0"
  "bluenviron/mediamtx:1.19.2"
  "eclipse-mosquitto:2.0.22"
)

NAME="UAV Mission Compute SDK"

set -euo pipefail

SCRIPT_NAME="$(basename "${0}")"
readonly SCRIPT_NAME
readonly LOG_PREFIX="[${SCRIPT_NAME}]"

# Color definitions
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[0;33m'
readonly BLUE='\033[0;34m'
readonly MAGENTA='\033[0;35m'
readonly CYAN='\033[0;36m'
readonly WHITE='\033[0;37m'
readonly BOLD='\033[1m'
readonly NC='\033[0m' # No Color

#######################################
# Print error message to stderr and exit
# Arguments:
#   Error message
#######################################
err() {
  echo -e "${RED}${LOG_PREFIX} ERROR: ${*}${NC}" >&2
  exit 1
}

#######################################
# Print info message to stdout
# Arguments:
#   Info message
#######################################
info() {
  echo -e "${BLUE}${LOG_PREFIX} INFO: ${*}${NC}"
}

#######################################
# Print success message to stdout
# Arguments:
#   Success message
#######################################
success() {
  echo -e "${GREEN}${LOG_PREFIX} SUCCESS: ${*}${NC}"
}

#######################################
# Print warning message to stdout
# Arguments:
#   Warning message
#######################################
warn() {
  echo -e "${YELLOW}${LOG_PREFIX} WARNING: ${*}${NC}"
}

#######################################
# Check if command exists
# Arguments:
#   Command name
# Returns:
#   0 if command exists, 1 otherwise
#######################################
command_exists() {
  command -v "${1}" >/dev/null 2>&1
}

check_supported_os() {
  local os_id="$1"
  local version="$2"

  case "${os_id}:${version}" in
    ubuntu:24.04|ubuntu:26.04)
      info "Supported operating system: Ubuntu ${version} LTS"
      ;;
    *)
      err "Unsupported operating system: ${os_id} ${version}. Use Ubuntu 24.04 LTS or Ubuntu 26.04 LTS."
      ;;
  esac
}

#######################################
# Get CPU information
# Outputs:
#   CPU model and core count
#######################################
get_cpu_info() {
  local cpu_model
  local cpu_cores
  
  if [[ -r /proc/cpuinfo ]]; then
    set +o pipefail
    cpu_model=$(grep "model name" /proc/cpuinfo | head -1 | cut -d: -f2 | sed 's/^ *//' 2>/dev/null)
    cpu_cores=$(nproc 2>/dev/null)
    set -o pipefail
    
    if [[ -n "${cpu_model}" && -n "${cpu_cores}" ]]; then
      echo -e "${GREEN}${BOLD}CPU:${NC} ${CYAN}${cpu_model}${NC} ${YELLOW}(${cpu_cores} cores)${NC}"
    else
      echo -e "${GREEN}${BOLD}CPU:${NC} ${RED}Information not available${NC}"
    fi
  else
    echo -e "${GREEN}${BOLD}CPU:${NC} ${RED}Information not available${NC}"
  fi
}

#######################################
# Get memory information
# Outputs:
#   Total and available memory in GB
#######################################
get_memory_info() {
  local total_mem
  local avail_mem
  
  if [[ -r /proc/meminfo ]]; then
    set +o pipefail
    total_mem=$(awk '/MemTotal/ {printf "%.1f", $2/1024/1024}' /proc/meminfo 2>/dev/null)
    avail_mem=$(awk '/MemAvailable/ {printf "%.1f", $2/1024/1024}' /proc/meminfo 2>/dev/null)
    set -o pipefail
    
    if [[ -n "${total_mem}" && -n "${avail_mem}" ]]; then
      echo -e "${GREEN}${BOLD}Memory:${NC} ${CYAN}${avail_mem}GB available${NC} ${WHITE}/${NC} ${MAGENTA}${total_mem}GB total${NC}"
    else
      echo -e "${GREEN}${BOLD}Memory:${NC} ${RED}Information not available${NC}"
    fi
  else
    echo -e "${GREEN}${BOLD}Memory:${NC} ${RED}Information not available${NC}"
  fi
}

#######################################
# Get storage information
# Outputs:
#   Root filesystem usage
#######################################
get_storage_info() {
  local storage_info
  
  if command_exists "df"; then
    set +o pipefail
    storage_info=$(df -h / | awk 'NR==2 {printf "%s used / %s total (%s available)", $3, $2, $4}' 2>/dev/null)
    set -o pipefail
    
    if [[ -n "${storage_info}" ]]; then
      local used total available
      used=$(echo "${storage_info}" | awk '{print $1}')
      total=$(echo "${storage_info}" | awk '{print $4}')
      available=$(echo "${storage_info}" | awk '{print $6}' | tr -d '()')
      echo -e "${GREEN}${BOLD}Storage:${NC} ${YELLOW}${used} used${NC} ${WHITE}/${NC} ${MAGENTA}${total} total${NC} ${WHITE}(${CYAN}${available} available${WHITE})${NC}"
    else
      echo -e "${GREEN}${BOLD}Storage:${NC} ${RED}Information not available${NC}"
    fi
  else
    echo -e "${GREEN}${BOLD}Storage:${NC} ${RED}Information not available${NC}"
  fi
}

#######################################
# Get Intel GPU information
# Outputs:
#   Intel GPU details if available
#######################################
get_intel_gpu_info() {
  local gpu_info=""
  
  if command_exists "lspci"; then
    set +o pipefail
    gpu_info=$(lspci | grep -i "vga\|display\|3d" | grep -i intel | head -1 2>/dev/null)
    set -o pipefail
    
    if [[ -n "${gpu_info}" ]]; then
      echo -e "${GREEN}${BOLD}Intel GPU:${NC} ${MAGENTA}${gpu_info##*: }${NC}"
    else
      echo -e "${GREEN}${BOLD}Intel GPU:${NC} ${RED}Not detected${NC}"
    fi
  elif command_exists "lshw"; then
    set +o pipefail
    gpu_info=$(lshw -c display 2>/dev/null | grep -i intel -A 5 | grep "product:" | head -1 2>/dev/null)
    set -o pipefail
    
    if [[ -n "${gpu_info}" ]]; then
      echo -e "${GREEN}${BOLD}Intel GPU:${NC} ${MAGENTA}${gpu_info##*: }${NC}"
    else
      echo -e "${GREEN}${BOLD}Intel GPU:${NC} ${RED}Not detected${NC}"
    fi
  else
    echo -e "${GREEN}${BOLD}Intel GPU:${NC} ${RED}Cannot detect (lspci/lshw not available)${NC}"
  fi
  
  if command_exists "intel_gpu_top"; then
    echo -e "${GREEN}${BOLD}Intel GPU Tools:${NC} ${CYAN}intel_gpu_top available${NC}"
  elif [[ -d /sys/class/drm/card0 ]]; then
    echo -e "${GREEN}${BOLD}Intel GPU Tools:${NC} ${CYAN}DRM interface available${NC}"
  fi
}

#######################################
# Check Docker installation and version
# Outputs:
#   Docker version information or installation status
#######################################
check_docker_installation() {
  echo -e "${GREEN}${BOLD}Docker Status:${NC}"
  
  if command_exists "docker"; then
    local docker_version
    set +o pipefail
    docker_version=$(docker --version 2>/dev/null | cut -d' ' -f3 | tr -d ',')
    set -o pipefail
    
    if [[ -n "${docker_version}" ]]; then
      echo -e "  ${CYAN}✓ Docker installed${NC} ${WHITE}(${docker_version})${NC}"
      
      if docker info >/dev/null 2>&1; then
        echo -e "  ${CYAN}✓ Docker service is running${NC}"
      else
        warn "Docker is installed but service is not running"
        echo -e "  ${YELLOW}Starting Docker service...${NC}"
        sudo systemctl start docker || err "Failed to start Docker service"
        sudo systemctl enable docker || warn "Failed to enable Docker service on boot"
      fi
    else
      warn "Docker command found but version check failed"
      return 1
    fi
  else
    warn "Docker is not installed"
    return 1
  fi
}

#######################################
# Install Docker and Docker Compose
# Installs Docker CE and Docker Compose if not present
#######################################
install_docker() {
  info "Installing Docker and Docker Compose..."
  
  info "Updating package list..."
  sudo apt-get update || err "Failed to update package list"
  
  info "Installing prerequisites..."
  sudo apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release || err "Failed to install prerequisites"
  
  info "Adding Docker's GPG key..."
  sudo mkdir -p /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg || err "Failed to add Docker GPG key"
  
  info "Adding Docker repository..."
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
    $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null || err "Failed to add Docker repository"
  
  sudo apt-get update || err "Failed to update package list after adding Docker repository"
  
  info "Installing Docker Engine..."
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin || err "Failed to install Docker"
  
  info "Adding user to docker group..."
  sudo usermod -aG docker $USER || warn "Failed to add user to docker group"
  
  sudo systemctl start docker || err "Failed to start Docker service"
  sudo systemctl enable docker || warn "Failed to enable Docker service on boot"
  
  success "Docker installation completed successfully!"
  warn "Please log out and log back in for group changes to take effect, or run 'newgrp docker'"
}

#######################################
# Check Docker Compose installation
# Outputs:
#   Docker Compose version or installation status
#######################################
check_docker_compose() {
  echo -e "${GREEN}${BOLD}Docker Compose Status:${NC}"
  
  if command_exists "docker" && docker compose version >/dev/null 2>&1; then
    local compose_version
    set +o pipefail
    compose_version=$(docker compose version 2>/dev/null | grep -o 'v[0-9]\+\.[0-9]\+\.[0-9]\+' | head -1)
    set -o pipefail
    
    if [[ -n "${compose_version}" ]]; then
      echo -e "  ${CYAN}✓ Docker Compose installed${NC} ${WHITE}(${compose_version})${NC}"
    else
      echo -e "  ${CYAN}✓ Docker Compose available${NC}"
    fi
  else
    warn "Docker Compose is not available"
    return 1
  fi
}

#######################################
# Pull required Docker images
# Downloads required container images
#######################################
pull_required_images() {
  info "Pulling required Docker images..."
  echo -e "${GREEN}${BOLD}Container Images:${NC}"
  
  for image in "${images[@]}"; do
    echo -e "  ${YELLOW}Pulling ${image}...${NC}"
    if docker pull "${image}" >/dev/null 2>&1; then
      echo -e "  ${CYAN}✓ ${image}${NC}"
    else
      warn "Failed to pull ${image}"
    fi
  done
  
  success "Docker image pull completed!"
}

#######################################
# Verify Docker images
# Lists the pulled images for verification
#######################################
verify_images() {
  echo -e "${GREEN}${BOLD}Installed Images:${NC}"
  
  for image in "${images[@]}"; do
    set +o pipefail
    local image_info
    image_info=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep "^${image}" | head -1)
    set -o pipefail

    if [[ -n "${image_info}" ]]; then
      echo -e "  ${CYAN}✓ ${image_info}${NC}"
    else
      echo -e "  ${RED}✗ ${image} not found${NC}"
    fi
  done
}

#######################################
# Create OEP directory if it doesn't exist
# Returns:
#   0 if directory exists or was created successfully
#######################################
create_oep_directory() {
  local oep_dir="$HOME/oep"
  
  if [[ ! -d "${oep_dir}" ]]; then
    info "Creating OEP directory at ${oep_dir}..."
    mkdir -p "${oep_dir}" || err "Failed to create OEP directory"
    success "OEP directory created successfully"
  else
    info "OEP directory already exists at ${oep_dir}"
  fi
  
  echo -e "${GREEN}${BOLD}OEP Directory:${NC} ${CYAN}${oep_dir}${NC}"
}

#######################################
# Clone git repository
# Arguments:
#   Repository URL
#   Branch name
#   Target directory name
#######################################
clone_repository() {
  local repo_url="$1"
  local branch="$2"
  local target_dir="$3"
  local oep_dir="$HOME/oep"
  local full_path="${oep_dir}/${target_dir}"
  
  if [[ -d "${full_path}" ]]; then
    warn "Directory ${target_dir} already exists, checking if it's the correct repository..."
    
    if [[ -d "${full_path}/.git" ]]; then
      local current_remote
      set +o pipefail
      current_remote=$(cd "${full_path}" && git remote get-url origin 2>/dev/null)
      set -o pipefail
      
      if [[ "${current_remote}" == "${repo_url}" ]]; then
        info "Repository ${target_dir} already exists, updating to branch ${branch}..."
        
        (cd "${full_path}" && git fetch origin && git checkout "${branch}" && git pull origin "${branch}") >/dev/null 2>&1 || {
          warn "Failed to update repository, removing and re-cloning..."
          rm -rf "${full_path}"
          clone_repository "$1" "$2" "$3"
          return $?
        }
        
        success "Repository ${target_dir} updated to branch ${branch}"
        return 0
      else
        warn "Directory ${target_dir} exists but points to different repository, removing..."
        rm -rf "${full_path}"
      fi
    else
      warn "Directory ${target_dir} exists but is not a git repository, removing..."
      rm -rf "${full_path}"
    fi
  fi
  
  info "Cloning ${repo_url} (branch: ${branch}) to ${target_dir}..."
  
  if git clone --branch "${branch}" "${repo_url}" "${full_path}" >/dev/null 2>&1; then
    success "Successfully cloned ${target_dir}"
    echo -e "  ${CYAN}✓ ${target_dir} (branch: ${branch})${NC}"
  else
    warn "Failed to clone ${repo_url}"
    echo -e "  ${RED}✗ ${target_dir} (failed)${NC}"
  fi
}

#######################################
# Clone required repositories
# Clones repositories from the predefined list
#######################################
clone_repositories() {
  info "Cloning required repositories..."
  echo -e "${GREEN}${BOLD}Git Repositories:${NC}"
  
  if ! command_exists "git"; then
    info "Git is not installed. Installing git..."
    sudo apt-get update || err "Failed to update package list"
    sudo apt-get install -y git || err "Failed to install git"
    success "Git installed successfully!"
  fi
  
  for repo in "${repositories[@]}"; do
    IFS='|' read -r repo_url branch target_dir <<< "${repo}"
    clone_repository "${repo_url}" "${branch}" "${target_dir}"
  done
}

#######################################
# Populate required .env credentials with generated values
# Fills UAV_ID, INFLUXDB_PASSWORD, INFLUXDB_TOKEN, INFLUXDB_ORG, and
# GRAFANA_PASSWORD if they are absent or empty, then prints a summary.
# Arguments:
#   Path to the .env file
#######################################
populate_env_credentials() {
  local env_file="$1"

  # Helper: set a key only when it is absent or blank
  set_if_empty() {
    local key="$1" value="$2"
    if ! grep -qE "^${key}=.+" "${env_file}" 2>/dev/null; then
      sed -i "/^${key}=/d" "${env_file}"
      echo "${key}=${value}" >> "${env_file}"
    fi
  }

  local uav_id="uav-1"
  local influxdb_password influxdb_token influxdb_org grafana_password
  influxdb_password="$(openssl rand -hex 16)"
  influxdb_token="$(openssl rand -hex 32)"
  influxdb_org="uav-sdk"
  grafana_password="$(openssl rand -hex 12)"

  set_if_empty "UAV_ID"            "${uav_id}"
  set_if_empty "INFLUXDB_PASSWORD" "${influxdb_password}"
  set_if_empty "INFLUXDB_TOKEN"    "${influxdb_token}"
  set_if_empty "INFLUXDB_ORG"      "${influxdb_org}"
  set_if_empty "GRAFANA_PASSWORD"  "${grafana_password}"

  echo ""
  echo -e "${BOLD}${CYAN}Generated Credentials (saved to ${env_file})${NC}"
  echo ""
}

#######################################
# Bring up the UAV Mission Compute SDK stack
# Starts the local simulation stack from the cloned Federal Aerospace package
#######################################
bring_up_uav_sdk() {
  local sdk_dir="$HOME/oep/federal-and-aerospace-ai-suite/uav-mission-compute-sdk"

  if [[ ! -d "${sdk_dir}" ]]; then
    err "UAV Mission Compute SDK directory not found at ${sdk_dir}"
  fi

  if ! command_exists "make"; then
    err "make is required to bring up the UAV Mission Compute SDK"
  fi

  info "Preparing UAV Mission Compute SDK in ${sdk_dir}..."
  (cd "${sdk_dir}" && make init) || err "Failed to initialize the UAV Mission Compute SDK environment"

  populate_env_credentials "${sdk_dir}/.env"

  info "Bringing up the UAV Mission Compute SDK stack..."
  (cd "${sdk_dir}" && make up-sim-camera) || err "Failed to bring up the UAV Mission Compute SDK stack"

  success "UAV Mission Compute SDK stack is up"
}

#######################################
# Verify Git Repositories
# Lists the cloned repositories for verification
#######################################
verify_repos() {
  echo -e "${GREEN}${BOLD}Installed Repos:${NC}"

  for repo in "${repositories[@]}"; do
    IFS='|' read -r repo_url branch target_dir <<< "${repo}"
    new_target_dir="$HOME/oep/${target_dir}"
    local repo_info
    if repo_info=$(git -C "${new_target_dir}" remote get-url origin 2>/dev/null) && [[ -n "${repo_info}" ]]; then
      echo -e "  ${CYAN}✓ ${target_dir}${NC}"
    else
      echo -e "  ${RED}✗ ${target_dir} not found${NC}"
    fi
  done
}

#######################################
# Show help message
#######################################
show_help() {
  echo -e "${BOLD}${CYAN}UAV Mission Compute SDK Installation Script${NC}"
  echo ""
  echo -e "${BOLD}Usage:${NC} $0 [OPTIONS]"
  echo "Supported hosts: Ubuntu 24.04 LTS and Ubuntu 26.04 LTS"
  echo ""
  echo -e "${BOLD}Options:${NC}"
  echo -e "  ${GREEN}--skip-system-check${NC}    Skip system resource verification"
  echo -e "  ${GREEN}--skip-docker${NC}          Skip Docker installation check"
  echo -e "  ${GREEN}--skip-images${NC}          Skip Docker image download"
  echo -e "  ${GREEN}--skip-git-clone${NC}       Skip git repository cloning"
  echo -e "  ${GREEN}--help${NC}                 Show this help message"
  echo ""
  echo -e "${BOLD}Examples:${NC}"
  echo -e "  $0                           # Full installation"
  echo -e "  $0 --skip-system-check       # Skip hardware check"
  echo -e "  $0 --skip-docker             # Only do system check and images"
  echo ""
}

#######################################
# Main function
#######################################
main() {
  local skip_system_check=false
  local skip_docker=false
  local skip_images=false
  local skip_git_clone=false
  
  # Parse command line arguments
  while [[ $# -gt 0 ]]; do
    case $1 in
      --skip-system-check)
        skip_system_check=true
        shift
        ;;
      --skip-docker)
        skip_docker=true
        shift
        ;;
      --skip-images)
        skip_images=true
        shift
        ;;
      --skip-git-clone)
        skip_git_clone=true
        shift
        ;;
      --help)
        show_help
        exit 0
        ;;
      *)
        err "Unknown option: $1. Use --help for usage information."
        ;;
    esac
  done
  info "UAV Mission Compute SDK Installation Script"
  local os_id os_version
  [[ -r /etc/os-release ]] || err "Cannot determine the host operating system: /etc/os-release is missing."
  IFS=: read -r os_id os_version < <(
    source /etc/os-release
    printf '%s:%s\n' "${ID:-unknown}" "${VERSION_ID:-unknown}"
  )
  check_supported_os "${os_id}" "${os_version}"
  echo -e "${BOLD}${BLUE}==================================================${NC}"
  
  # System Requirements Check
  if [[ "${skip_system_check}" != "true" ]]; then
    echo -e "${BOLD}${CYAN}System Requirements Check${NC}"
    echo -e "${BOLD}${BLUE}==================================================${NC}"
    
    get_cpu_info
    get_memory_info
    get_storage_info
    get_intel_gpu_info
    
    echo -e "${BOLD}${BLUE}==================================================${NC}"
  else
    info "Skipping system requirements check"
  fi
  
  # Docker Installation and Setup
  if [[ "${skip_docker}" != "true" ]]; then
    echo -e "${BOLD}${CYAN}Docker Installation and Setup${NC}"
    echo -e "${BOLD}${BLUE}==================================================${NC}"
    
    if ! check_docker_installation; then
      info "Docker not found. Installing Docker..."
      install_docker
      
      if check_docker_installation; then
        success "Docker installation verified!"
      else
        err "Docker installation failed or verification unsuccessful"
      fi
    fi
    
    if ! check_docker_compose; then
      warn "Docker Compose not available. This is included with modern Docker installations."
    fi
    
    echo -e "${BOLD}${BLUE}==================================================${NC}"
  else
    info "Skipping Docker installation check"
    if [[ "${skip_images}" != "true" ]] && ! command_exists "docker"; then
      err "Docker is required for image operations but was skipped. Please install Docker first."
    fi
  fi
  
  # Container Image Setup
  if [[ "${skip_images}" != "true" ]]; then
    echo -e "${BOLD}${CYAN}Container Image Setup${NC}"
    echo -e "${BOLD}${BLUE}==================================================${NC}"
    
    pull_required_images
    
    echo ""
    echo -e "${BOLD}${BLUE}==================================================${NC}"
  else
    info "Skipping Docker image download"
  fi
  
  # Git Repository Setup
  if [[ "${skip_git_clone}" != "true" ]]; then
    echo -e "${BOLD}${CYAN}Git Repository Setup${NC}"
    echo -e "${BOLD}${BLUE}==================================================${NC}"
    
    create_oep_directory
    
    echo ""
    clone_repositories
    
    echo -e "${BOLD}${BLUE}==================================================${NC}"
  else
    info "Skipping git repository cloning"
  fi

  echo -e "${BOLD}${CYAN}UAV Mission Compute SDK Bring-Up${NC}"
  echo -e "${BOLD}${BLUE}==================================================${NC}"

  bring_up_uav_sdk

  echo -e "${BOLD}${BLUE}==================================================${NC}"

  # Container Image Setup
  if [[ "${skip_images}" != "true" ]]; then
      verify_images
  fi
  
  # Git Repository Setup
  if [[ "${skip_git_clone}" != "true" ]]; then
    verify_repos
  fi
  
  echo -e "${BOLD}${BLUE}==================================================${NC}"
  success "${NAME} installation completed successfully!"
  echo -e "${BOLD}${BLUE}==================================================${NC}"
  
  echo ""
  info "Next steps:"
  info "1. Navigate to ${HOME}/oep/federal-and-aerospace-ai-suite/uav-mission-compute-sdk to explore the SDK"

}

# Execute main function if script is run directly
main "$@"
