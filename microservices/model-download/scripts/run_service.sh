#!/bin/bash

# Default values
DEFAULT_MODEL_PATH="$HOME/models/"
BUILD=false
REBUILD=false
PLUGINS=""
MODEL_PATH=""
TAG="latest"
REGISTRY=""
ACTION="up"

# Function to display script usage
show_usage() {
    echo "Usage: $0 [options] [action]"
    echo "Actions:"
    echo "  up                     Start the services (default)"
    echo "  down                   Stop the services"
    echo "Options:"
    echo "  --build                Build the Docker image before running"
    echo "  --rebuild              Force rebuild the Docker image without cache"
    echo "  --model-path <path>    Set custom model path (default: $DEFAULT_MODEL_PATH)"
    echo "  --plugins <list>       Comma-separated list of plugins to enable (e.g., huggingface,ollama,ultralytics)"
    echo "  --tag <tag>            Docker image tag (default: latest)"
    echo "  --registry <registry>  Docker registry prefix (default: none)"
    echo "  --help                 Show this help message"
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
            shift
            ;;
        --rebuild)
            REBUILD=true
            BUILD=true
            shift
            ;;
        --model-path)
            if [[ -n "$2" && "$2" != --* ]]; then
                MODEL_PATH="$2"
                shift 2
            else
                echo "Error: --model-path requires a path argument"
                exit 1
            fi
            ;;
        --plugins)
            if [[ -n "$2" && "$2" != --* ]]; then
                PLUGINS="$2"
                shift 2
            else
                echo "Error: --plugins requires a comma-separated list"
                exit 1
            fi
            ;;
        --tag)
            if [[ -n "$2" && "$2" != --* ]]; then
                TAG="$2"
                shift 2
            else
                echo "Error: --tag requires a value"
                exit 1
            fi
            ;;
        --registry)
            if [[ -n "$2" && "$2" != --* ]]; then
                REGISTRY="$2"
                # Make sure registry ends with a slash if not empty
                if [[ -n "$REGISTRY" && ! "$REGISTRY" == */ ]]; then
                    REGISTRY="${REGISTRY}/"
                fi
                shift 2
            else
                echo "Error: --registry requires a value"
                exit 1
            fi
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option or action: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Change to the docker directory first for both actions
cd "$(dirname "$0")/../docker" || { echo "Failed to change directory to ../docker"; exit 1; }

# Skip model path setup and other operations for "down" action
if [[ "$ACTION" != "down" ]]; then
    # If model path is not provided, use default
    if [[ -z "$MODEL_PATH" ]]; then
        MODEL_PATH="$DEFAULT_MODEL_PATH"
    fi

    # Setup the model path (similar to setup_model_path.sh)
    echo "Setting up model path: $MODEL_PATH"

    if [[ "$MODEL_PATH" != /* ]]; then
        MODEL_PATH="$PWD/$MODEL_PATH"
        echo "Relative path provided. Using absolute path: $MODEL_PATH"
    fi

    # Check if MODEL_PATH exists
    if [ -e "$MODEL_PATH" ]; then
        # If it exists, check the owner
        if [ "$(stat -c '%U:%G' "$MODEL_PATH")" != "root:root" ]; then
            echo "$MODEL_PATH exists in host..."
        else
            # If owned by root:root, delete and recreate it
            echo "$MODEL_PATH exists and is owned by root:root. Deleting it and recreate..."
            sudo rm -rf "$MODEL_PATH"
            mkdir -p "$MODEL_PATH"
            echo "Recreated $MODEL_PATH with correct permissions."
        fi
    else
        # If it doesn't exist, create it
        echo "$MODEL_PATH does not exist. Creating it..."
        mkdir -p "$MODEL_PATH"
    fi

    # Get the current user group ID for Docker permissions
    USER_GROUP_ID=$(id -g)

    # Export environment variables for docker-compose
    export TAG="$TAG"
    export REGISTRY="$REGISTRY"
    export USER_GROUP_ID="$USER_GROUP_ID"
    export MODEL_PATH="$MODEL_PATH"
    export ENABLED_PLUGINS="$PLUGINS"

    # Generate environment file for docker-compose
    echo "Generating environment settings..."
    cat > ../.env << EOF
TAG=$TAG
REGISTRY=$REGISTRY
USER_GROUP_ID=$USER_GROUP_ID
MODEL_PATH=$MODEL_PATH
ENABLED_PLUGINS=$PLUGINS
EOF
fi

# Handle the action
case "$ACTION" in
    up)
        # Build the Docker image if requested
        if [[ "$BUILD" == true ]]; then
            BUILD_COMMAND="docker compose build"
            
            # Add no-cache option if rebuild is requested
            if [[ "$REBUILD" == true ]]; then
                BUILD_COMMAND="$BUILD_COMMAND --no-cache"
            fi
            
            echo "Building Docker image: $BUILD_COMMAND"
            eval "$BUILD_COMMAND" || { echo "Docker build failed"; exit 1; }
        fi

        # Run the Docker container
        echo "Starting model download service..."
        if docker compose ps | grep -q "model_download"; then
            echo "Service is already running. Stopping first..."
            docker compose down
        fi

        docker compose up -d

        echo "Model download service is running."
        echo "- Model path: $MODEL_PATH"
        if [[ -n "$PLUGINS" ]]; then
            echo "- Enabled plugins: $PLUGINS"
        fi
        echo "- Access the API at http://localhost:8200"
        echo "- View logs with: docker logs model_download"
        ;;
    down)
        # For down action, we only need to stop the services
        echo "Stopping model download service..."
        docker compose down
        echo "Model download service stopped."
        ;;
    *)
        echo "Unknown action: $ACTION"
        show_usage
        exit 1
        ;;
esac