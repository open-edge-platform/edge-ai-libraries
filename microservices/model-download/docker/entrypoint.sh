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

# Temporary directory for parallel job coordination
PARALLEL_TMP_DIR=$(mktemp -d)
# Cleanup temp dir on exit
trap 'rm -rf "${PARALLEL_TMP_DIR}"' EXIT

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

# Function to install dependencies for a single plugin.
# Output goes directly to stdout (the caller pipes it through awk for prefixing).
# Results (exit code and any exported env vars) are written to status/env files
# under PARALLEL_TMP_DIR so the parent shell can pick them up after all jobs finish.
install_dependencies() {
    local plugin=$1
    local status_file="${PARALLEL_TMP_DIR}/${plugin}.status"
    local env_file="${PARALLEL_TMP_DIR}/${plugin}.env"

    echo -e "${CYAN}=======================================${NC}"
    echo -e "${CYAN}   Preparing ${plugin} plugin${NC}"
    echo -e "${CYAN}=======================================${NC}"

    case $plugin in
        openvino)
            # Normalize OVMS_RELEASE_TAG to URL-friendly format (releases/YYYY/M)
            OVMS_RELEASE_TAG="${OVMS_RELEASE_TAG:-v2025.4.1}"
            DEFAULT_OVMS_TAG="v2025.4.1"
            echo -e "${BLUE}INFO:${NC} Input OVMS release tag: ${OVMS_RELEASE_TAG}"

            # Check if using default version - skip downloads and use pyproject.toml pinned versions
            if [[ "${OVMS_RELEASE_TAG}" == "${DEFAULT_OVMS_TAG}" ]]; then
                echo -e "${BLUE}INFO:${NC} Using default OVMS version (${OVMS_RELEASE_TAG}). Skipping downloads."
                echo -e "${BLUE}INFO:${NC} Dependencies from pyproject.toml will be used (pre-pinned for OVMS 2025.4.1)"
                EXPORT_SCRIPT_URL="https://raw.githubusercontent.com/openvinotoolkit/model_server/v2026.0/demos/common/export_models/export_model.py"
                mkdir -p /opt/scripts
                if curl -fsSL -o /opt/scripts/export_model.py "${EXPORT_SCRIPT_URL}"; then
                    echo -e "${GREEN} SUCCESS:${NC} export_model.py downloaded for OVMS ${OVMS_RELEASE_TAG}"
                else
                    echo -e "${YELLOW} WARNING:${NC} Failed to download export_model.py. Falling back to bundled script."
                fi
                echo "OVMS_REQUIREMENTS_FILE=" >> "${env_file}"
                echo "OVMS_CUSTOM_TAG=false" >> "${env_file}"
            # Only process non-default versions if tag is in vYYYY.M.P format
            elif [[ "${OVMS_RELEASE_TAG}" =~ ^v[0-9]{4}\.[0-9]+\.[0-9]+$ ]]; then
                echo -e "${BLUE}INFO:${NC} Custom OVMS version detected. Downloading version-specific files for: ${OVMS_RELEASE_TAG}"

                # Use tag directly in URL (v2025.4.1 -> releases/2025/4)
                OVMS_URL_TAG="releases/${OVMS_RELEASE_TAG:1:4}/${OVMS_RELEASE_TAG:6:1}"

                # Download export_model.py
                EXPORT_SCRIPT_URL="https://raw.githubusercontent.com/openvinotoolkit/model_server/${OVMS_URL_TAG}/demos/common/export_models/export_model.py"
                mkdir -p /opt/scripts
                if curl -fsSL -o /opt/scripts/export_model.py "${EXPORT_SCRIPT_URL}"; then
                    echo -e "${GREEN} SUCCESS:${NC} export_model.py downloaded for OVMS ${OVMS_RELEASE_TAG}"
                else
                    echo -e "${YELLOW} WARNING:${NC} Failed to download export_model.py. Falling back to bundled script."
                fi

                # Download requirements.txt - used INSTEAD of pyproject.toml openvino extra to avoid conflicts
                REQUIREMENTS_URL="https://raw.githubusercontent.com/openvinotoolkit/model_server/${OVMS_URL_TAG}/demos/common/export_models/requirements.txt"
                REQUIREMENTS_FILE="/tmp/openvino_requirements_${OVMS_RELEASE_TAG//[\.\/ ]/_}.txt"
                if curl -fsSL -o "${REQUIREMENTS_FILE}" "${REQUIREMENTS_URL}"; then
                    echo -e "${GREEN} SUCCESS:${NC} OVMS requirements.txt downloaded"
                    echo "OVMS_REQUIREMENTS_FILE=${REQUIREMENTS_FILE}" >> "${env_file}"
                    echo "OVMS_CUSTOM_TAG=true" >> "${env_file}"
                else
                    echo -e "${YELLOW} WARNING:${NC} Failed to download requirements.txt. Falling back to pyproject.toml defaults."
                    echo "OVMS_REQUIREMENTS_FILE=" >> "${env_file}"
                    echo "OVMS_CUSTOM_TAG=false" >> "${env_file}"
                fi
            else
                echo -e "${RED} ERROR:${NC} Invalid OVMS_RELEASE_TAG format '${OVMS_RELEASE_TAG}'. Expected format: vYYYY.M.P (e.g. v2025.4.1)"
                echo "OVMS_REQUIREMENTS_FILE=" >> "${env_file}"
                echo "OVMS_CUSTOM_TAG=false" >> "${env_file}"
            fi
            echo "0" > "${status_file}"
            ;;
        huggingface)
            echo -e "${BLUE}INFO:${NC} HuggingFace dependencies will be installed via uv sync"
            echo "0" > "${status_file}"
            ;;
        ollama)
            echo -e "${BLUE}INFO:${NC} Installing Ollama binary..."
            OLLAMA_VERSION="v0.17.4"
            OLLAMA_ARCHIVE="${PARALLEL_TMP_DIR}/ollama-linux-amd64.tar.zst"
            OLLAMA_URL="https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-linux-amd64.tar.zst"

            # Ensure zstd is available
            if ! command -v zstd &> /dev/null && ! command -v unzstd &> /dev/null; then
                echo -e "${RED} ERROR:${NC} zstd is not installed. Please install zstd package."
                echo "1" > "${status_file}"
                return 1
            fi

            mkdir -p /opt/bin

            echo -e "${BLUE}INFO:${NC} Downloading and extracting Ollama ${OLLAMA_VERSION} binary only..."
            # Stream the archive and extract only the ollama binary - avoids writing full archive to disk
            if ! curl -fSL "${OLLAMA_URL}" | tar --use-compress-program=unzstd -xf - -C /opt/bin --strip-components=1 bin/ollama; then
                echo -e "${RED} ERROR:${NC} Failed to download or extract Ollama binary"
                echo "1" > "${status_file}"
                return 1
            fi

            chmod +x /opt/bin/ollama

            # Verify ollama binary is present and executable
            if [ -x "/opt/bin/ollama" ]; then
                echo -e "${GREEN} SUCCESS:${NC} Ollama binary ${OLLAMA_VERSION} installed successfully to /opt/bin/ollama"
                /opt/bin/ollama --version 2>&1 | grep -i "version" || true
            else
                echo -e "${RED} ERROR:${NC} Ollama binary not found or not executable at /opt/bin/ollama"
                echo "1" > "${status_file}"
                return 1
            fi
            echo "0" > "${status_file}"
            ;;
        ultralytics)
            echo -e "${BLUE}INFO:${NC} Downloading Ultralytics public models script from GitHub"
            mkdir -p /opt/scripts
            if curl -fsSL -o /opt/scripts/download_public_models.sh https://raw.githubusercontent.com/open-edge-platform/dlstreamer/v2026.0.0/samples/download_public_models.sh; then
                chmod +x /opt/scripts/download_public_models.sh
                echo -e "${GREEN} SUCCESS:${NC} Ultralytics public models script downloaded to /opt/scripts/download_public_models.sh"
            else
                echo -e "${RED} ERROR:${NC} Failed to download Ultralytics public models script"
                echo "1" > "${status_file}"
                return 1
            fi
            echo -e "${BLUE}INFO:${NC} Ultralytics dependencies will be installed via uv sync"
            echo "0" > "${status_file}"
            ;;
        geti)
            echo -e "${BLUE}INFO:${NC} Geti plugin dependencies will be installed via uv sync"
            echo -e "${BLUE}INFO:${NC} Geti plugin requires: GETI_HOST, GETI_TOKEN, GETI_SERVER_API_VERSION"
            echo "0" > "${status_file}"
            ;;
        hls)
            print_info "HLS plugin dependencies will be installed via uv sync"
            echo "0" > "${status_file}"
            ;;
        *)
            echo -e "${RED} ERROR:${NC} Unknown plugin: $plugin"
            echo "1" > "${status_file}"
            return 1
            ;;
    esac
}

run_plugins_parallel() {
    local plugins=("$@")
    local pids=()

    print_header "Installing plugin dependencies in parallel"

    for plugin in "${plugins[@]}"; do
        # Pipe output through awk for real-time prefixed streaming
        (install_dependencies "${plugin}") 2>&1 \
            | awk -v p="${plugin}" '{ print "[" p "] " $0; fflush() }' &
        pids+=("$!")
        print_info "Started setup for plugin: ${plugin}"
    done

    # Wait for all background pipeline jobs to finish
    for pid in "${pids[@]}"; do
        wait "${pid}" || true
    done

    # Check status files written by each subshell
    local failed_plugins=()
    for plugin in "${plugins[@]}"; do
        local status_file="${PARALLEL_TMP_DIR}/${plugin}.status"
        local exit_code=1
        if [ -f "${status_file}" ]; then
            exit_code=$(cat "${status_file}")
        fi
        if [ "${exit_code}" != "0" ]; then
            failed_plugins+=("${plugin}")
        fi
    done

    # Source any env vars written by subshells (e.g. OVMS_REQUIREMENTS_FILE)
    for plugin in "${plugins[@]}"; do
        local env_file="${PARALLEL_TMP_DIR}/${plugin}.env"
        if [ -f "${env_file}" ]; then
            # shellcheck disable=SC1090
            source "${env_file}"
        fi
    done

    if [ "${#failed_plugins[@]}" -gt 0 ]; then
        print_error "The following plugins failed to set up: ${failed_plugins[*]}"
        exit 1
    fi

    print_success "All plugin setups completed"
}

# Parse arguments
PLUGINS=""
START_SERVICE=true
EXTRA_ARGS=()

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
AVAILABLE_PLUGINS=("openvino" "huggingface" "ollama" "ultralytics" "geti" "hls")

# Install plugin-specific dependencies (in parallel)
if [ "$PLUGINS" = "all" ]; then
    print_info "Installing ALL plugins"
    run_plugins_parallel "${AVAILABLE_PLUGINS[@]}"
    for plugin in "${AVAILABLE_PLUGINS[@]}"; do
        if [[ "$plugin" == "openvino" && "${OVMS_CUSTOM_TAG}" == "true" ]]; then
            print_info "Skipping openvino uv extra — dependencies will be installed from openvino model server requirements.txt"
        elif [[ "$plugin" == "hls" ]]; then
            print_info "Skipping hls uv extra — HLS dependencies are installed in an isolated venv at first request"
        else
            EXTRA_ARGS+=("--extra" "$plugin")
        fi
    done
    echo "ACTIVATED_PLUGINS=all" > "$PLUGINS_ENV_FILE"
    print_success "All plugins are activated"
else
    # Split comma-separated plugins and run them in parallel
    IFS=',' read -ra PLUGIN_LIST <<< "$PLUGINS"
    # Trim whitespace from each plugin name
    TRIMMED_PLUGINS=()
    for plugin in "${PLUGIN_LIST[@]}"; do
        TRIMMED_PLUGINS+=("$(echo "$plugin" | xargs)")
    done

    run_plugins_parallel "${TRIMMED_PLUGINS[@]}"

    for plugin in "${TRIMMED_PLUGINS[@]}"; do
        if [[ "$plugin" == "openvino" && "${OVMS_CUSTOM_TAG}" == "true" ]]; then
            print_info "Skipping openvino uv extra — dependencies will be installed from OpenVINO model server requirements.txt"
        elif [[ "$plugin" == "hls" ]]; then
            print_info "Skipping hls uv extra — HLS dependencies are installed in an isolated venv at first request"
        else
            EXTRA_ARGS+=("--extra" "$plugin")
        fi
    done

    echo "ACTIVATED_PLUGINS=$PLUGINS" > "$PLUGINS_ENV_FILE"
    print_success "Activated plugins: $PLUGINS"
fi

# Sync dependencies using UV
print_header "Syncing dependencies with UV"
cd /opt
print_info "Installing dependencies from pyproject.toml..."

# ollama to PATH if it's not already there
export PATH="/opt/bin/:$PATH"

if uv sync "${EXTRA_ARGS[@]}"; then
    print_success "Dependencies synced successfully"
    
    # If OpenVINO was installed and we have a requirements file, install OpenVINO-specific pins
    if [ -n "${OVMS_REQUIREMENTS_FILE}" ] && [ -f "${OVMS_REQUIREMENTS_FILE}" ]; then
        print_header "Installing OpenVINO dependencies"
        print_info "Installing from: ${OVMS_REQUIREMENTS_FILE}"
        if uv pip install -r "${OVMS_REQUIREMENTS_FILE}"; then
            print_success "OpenVINO dependencies installed successfully"
        else
            print_warning "Failed to install OpenVINO dependencies, continuing with base versions"
        fi
    fi
    
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
