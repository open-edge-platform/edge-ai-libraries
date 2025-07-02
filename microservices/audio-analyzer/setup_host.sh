#!/bin/bash

# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

# Color codes for terminal output
RED='\033[0;31m'
NC='\033[0m'

# Parse command line arguments
DEBUG=false
RELOAD=false
for arg in "$@"
do
    case $arg in
        --debug|-d)
        DEBUG=true
        shift
        ;;
        --reload|-r)
        RELOAD=true
        shift
        ;;
    esac
done

if [ "$DEBUG" = true ]; then
    export DEBUG=true
    echo "Debug mode enabled"
fi

if [ "$RELOAD" = true ]; then
    RELOAD_ARG="--reload"
    echo "Reload mode enabled"
else
    RELOAD_ARG=""
    echo "Reload mode disabled"
fi

export STORAGE_BACKEND=local
echo "Using ${STORAGE_BACKEND} storage backend"

echo "Configuring required environment variables..."
export INTEL_OPENVINO_DIR=/opt/intel/openvino
export LD_LIBRARY_PATH=/opt/intel/openvino/runtime/lib/intel64:/opt/intel/openvino/runtime/3rdparty/tbb/lib:/opt/intel/openvino/runtime/3rdparty/hddl/lib:$LD_LIBRARY_PATH
export PYTHONPATH=/opt/intel/openvino/python:$PYTHONPATH

export WHISPER_OPENVINO=1

export GGML_MODEL_DIR=/tmp/audio_analyzer_model/ggml
export OPENVINO_MODEL_DIR=/tmp/audio_analyzer_model/openvino
export ENABLED_WHISPER_MODELS=${ENABLED_WHISPER_MODELS}

if [ -z "$ENABLED_WHISPER_MODELS" ]; then
    echo -e "${RED}ERROR: No models specified. Please set ENABLED_WHISPER_MODELS environment variable.${NC}"
    exit 1
fi

echo "==== Audio Analyzer Service Setup ===="
echo "Installing system dependencies..."

sudo apt-get update && sudo apt-get install -y \
    build-essential \
    git \
    curl \
    wget \
    cmake \
    ffmpeg \
    python3-pip \
    python3-dev \
    python3-venv

echo "Setting up Intel repositories for oneAPI and GPU   ..."

wget -qO- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | sudo gpg --dearmor | sudo tee /usr/share/keyrings/intel-oneapi-archive-keyring.gpg > /dev/null
sudo echo "deb [signed-by=/usr/share/keyrings/intel-oneapi-archive-keyring.gpg] https://apt.repos.intel.com/oneapi all main" | sudo tee /etc/apt/sources.list.d/oneAPI.list

echo "Installing Intel oneAPI and OpenVINO dependencies..."
sudo apt-get update && sudo apt-get install -y \
    intel-oneapi-runtime-opencl \
    intel-oneapi-runtime-compilers \
    intel-oneapi-runtime-libs \
    intel-oneapi-runtime-dpcpp-cpp \
    intel-oneapi-python


echo "Creating directories for models..."
mkdir -p /tmp/audio_analyzer_model/ggml
mkdir -p /tmp/audio_analyzer_model/openvino

echo "Installing Poetry 1.8.3..."
if ! command -v poetry &> /dev/null; then
    curl -sSL https://install.python-poetry.org | python3 - --version 1.8.3
    export PATH="$HOME/.local/bin:$PATH"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi

# Navigate to the project directory
cd "$(dirname "$0")"

poetry config virtualenvs.create true
poetry config virtualenvs.in-project true
poetry lock --no-update

echo "Installing project dependencies with Poetry..."
poetry install --no-interaction --no-ansi

echo "==== Setup complete! ===="
echo "Starting the Audio Analyzer service..."
echo "You can access the API at http://localhost:8000/docs"

poetry run uvicorn audio_analyzer.main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 200 $RELOAD_ARG