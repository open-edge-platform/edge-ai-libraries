#!/bin/bash
set -e

# Define color codes for messages
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Store which plugins are activated for runtime checks
PLUGINS_ENV_FILE="/opt/activated_plugins.env"

# Function to print status messages
print_success() {
    echo -e "${GREEN} SUCCESS:${NC} $1"
}

print_error() {
    echo -e "${RED} ERROR:${NC} $1"
}

print_info() {
    echo -e "${BLUE}INFO:${NC} $1"
}

print_warning() {
    echo -e "${YELLOW} WARNING:${NC} $1"
}

print_header() {
    echo -e "${CYAN}=======================================${NC}"
    echo -e "${CYAN}   $1${NC}"
    echo -e "${CYAN}=======================================${NC}"
}

# Function to install dependencies for specific plugins
install_dependencies() {
    local plugin=$1
    print_header "Preparing $plugin plugin"
    
    case $plugin in
        openvino)
            print_info "OpenVINO dependencies will be installed via uv sync"
            ;;
        huggingface)
            print_info "HuggingFace dependencies will be installed via uv sync"
            # Additional setup can be added here if needed
            ;;
        ollama)
            print_info "Installing Ollama binary..."            
            # Install Ollama binary
            if curl -LO https://ollama.com/download/ollama-linux-amd64.tgz && \
               tar -xzf ollama-linux-amd64.tgz -C "/opt/" && \
               rm ollama-linux-amd64.tgz && \
               chmod +x "/opt/bin/ollama" ; then
                print_success "Ollama binary installed successfully to /opt/bin/ollama"
            else
                print_error "Failed to install Ollama binary"
                return 1
            fi
            ;;
        ultralytics)
            print_info "Downloading Ultralytics public models script from GitHub"
            mkdir -p /opt/scripts
            if curl -fsSL -o /opt/scripts/download_public_models.sh https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/libraries/dl-streamer/samples/download_public_models.sh; then
                chmod +x /opt/scripts/download_public_models.sh
                print_success "Ultralytics public models script downloaded to /opt/scripts/download_public_models.sh"
            else
                print_error "Failed to download Ultralytics public models script"
                return 1
            fi
            print_info "Ultralytics dependencies will be installed via uv sync"
            # Additional setup can be added here if needed
            ;;
        *)
            print_error "Unknown plugin: $plugin"
            return 1
            ;;
    esac
}

# Parse arguments
PLUGINS=""
START_SERVICE=true

while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --plugins)
            PLUGINS="$2"
            shift
            shift
            ;;
        --no-start)
            START_SERVICE=false
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Define all available plugins in the application
AVAILABLE_PLUGINS=("openvino" "huggingface" "ollama" "ultralytics")

# Install plugin-specific dependencies
print_header "Installing plugin dependencies"
if [ "$PLUGINS" = "all" ]; then
    print_info "Installing ALL plugins"
    
    # Install dependencies for all available plugins
    for plugin in "${AVAILABLE_PLUGINS[@]}"; do
        install_dependencies "$plugin"
    done

    echo "ACTIVATED_PLUGINS=all" > "$PLUGINS_ENV_FILE"
    print_success "All plugins are activated"
else
    # Split comma-separated plugins and install dependencies for each
    IFS=',' read -ra PLUGIN_LIST <<< "$PLUGINS"
    echo "ACTIVATED_PLUGINS=$PLUGINS" > "$PLUGINS_ENV_FILE"
    
    for plugin in "${PLUGIN_LIST[@]}"; do
        install_dependencies "$plugin"
    done
    
    print_success "Activated plugins: $PLUGINS"
fi

# Sync dependencies using UV
print_header "Syncing dependencies with UV"
cd /opt
print_info "Installing dependencies from pyproject.toml..."

# Add UV and ollama to PATH if it's not already there
export PATH="/usr/local/bin:$HOME/.local/bin:/opt/bin/:$PATH"

# Build the list of --extra arguments from the activated plugins
EXTRA_ARGS=()
if [ "$PLUGINS" = "all" ]; then
    for plugin in "${AVAILABLE_PLUGINS[@]}"; do
        EXTRA_ARGS+=(--extra "$plugin")
    done
else
    for plugin in "${PLUGIN_LIST[@]}"; do
        EXTRA_ARGS+=(--extra "$plugin")
    done
fi

if uv sync "${EXTRA_ARGS[@]}"; then
    print_success "Dependencies synced successfully"
    # Activate the virtual environment created by uv sync
    if [ -d "/opt/.venv" ]; then
        print_info "Activating virtual environment"
        source /opt/.venv/bin/activate
    fi
else
    print_error "Failed to sync dependencies"
    exit 1
fi

# Start the service if requested
if [ "$START_SERVICE" = true ]; then
    print_header "Starting Model Download Service"
    cd /opt
    print_info "Launching service at http://0.0.0.0:8000"
    echo -e "${GREEN}===============================================${NC}"
    echo -e "${GREEN}  Model Download Service is now starting up    ${NC}"
    echo -e "${GREEN}===============================================${NC}"
    exec uvicorn src.api.main:app --host 0.0.0.0 --port 8000
else
    print_warning "Service start skipped due to --no-start flag"
    exec "$@"
fi