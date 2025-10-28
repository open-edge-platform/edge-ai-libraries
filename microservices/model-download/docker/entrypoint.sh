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
    print_header "Installing dependencies for $plugin plugin"
    
    # First, update the pyproject.toml file to include the dependencies
    update_pyproject() {
        local dep_group=$1
        local dependencies=$2
        
        print_info "Updating pyproject.toml with $dep_group dependencies"
        
        # Check if the dependency group already exists
        if grep -q "\[tool.poetry.group.$dep_group\]" /opt/pyproject.toml; then
            print_info "Dependency group $dep_group already exists in pyproject.toml"
        else
            # Add the dependency group
            echo -e "\n[tool.poetry.group.$dep_group]\noptional = true\n\n[tool.poetry.group.$dep_group.dependencies]$dependencies" >> /opt/pyproject.toml
            print_success "Added dependency group $dep_group to pyproject.toml"
        fi
    }
    
    case $plugin in
        openvino)
            print_info "Installing OpenVINO dependencies..."
            
            # Update pyproject.toml
            update_pyproject "openvino" "\nopenvino = \"^2025.0.0\"\nopenvino-dev = \"^2025.0.0\""

            if pip install --user --no-cache-dir -r https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/heads/releases/2025/3/demos/common/export_models/requirements.txt; then
                print_success "OpenVINO dependencies installed successfully"
            else
                print_error "Failed to install OpenVINO dependencies"
                return 1
            fi
            ;;
        huggingface)
            print_info "Installing HuggingFace dependencies..."
            
            # Update pyproject.toml
            update_pyproject "huggingface" "\nhuggingface_hub = {version = \"0.35.3\", extras = [\"cli\", \"hf-transfer\", \"hf-xet\"]}\nsentence-transformers = \"5.1.1\"\neinops = \"0.8.1\""
            
            if pip install --user --no-cache-dir "huggingface_hub[cli,hf-transfer,hf-xet]==0.35.3" sentence-transformers==5.1.1 einops==0.8.1; then
                print_success "HuggingFace dependencies installed successfully"
            else
                print_error "Failed to install HuggingFace dependencies"
                return 1
            fi
            ;;
        ollama)
            print_info "Installing Ollama dependencies..."            
            # Install Ollama binary as non-root user
            print_info "Installing Ollama binary..."
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
            print_info "Installing Ultralytics dependencies..."
            
            # Update pyproject.toml
            update_pyproject "ultralytics" "\nultralytics = \"8.3.196\"\ntorch = \"2.7.1\"\ntorchvision = \"^0.18.1\""
            
            if pip install --user --no-cache-dir ultralytics==8.3.196 torch==2.7.1 torchvision; then
                print_success "Ultralytics dependencies installed successfully"
            else
                print_error "Failed to install Ultralytics dependencies"
                return 1
            fi
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

# Update the poetry.lock file based on pyproject.toml
print_header "Updating poetry.lock"
cd /opt
print_info "Generating poetry.lock from pyproject.toml..."

# Add Poetry and ollama to PATH if it's not already there
export PATH="$HOME/.local/bin:/opt/bin/:$PATH"

if command -v poetry &> /dev/null; then
    if poetry lock --no-update; then
        print_success "poetry.lock updated successfully"
        
        # Activate the Python virtual environment if it exists
        if [ -d "/opt/.venv" ]; then
            print_info "Activating Python virtual environment"
            source /opt/.venv/bin/activate
        fi
    else
        print_warning "Failed to update poetry.lock, but continuing anyway"
    fi
else
    print_warning "Poetry command not found, skipping lock file update"
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