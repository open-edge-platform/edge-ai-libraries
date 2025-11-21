#!/bin/bash

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate the virtual environment
source venv/bin/activate

# Setup OpenTelemetry and OpenLit Configurations 
export OTEL_SERVICE_NAME=document-summarization
export OTEL_SERVICE_ENV=development
export OTEL_SERVICE_VERSION=1.0.0 

# Setup no_proxy
export no_proxy=${no_proxy},ovms-service,docsum-api,docsum-ui,localhost

# Setup the OVMS configuration
export WEIGHT_FORMAT=int8
export TARGET_DEVICE=CPU

# Set Hugging Face cache directory to a local, writable path
export HF_HOME="$PWD/.hf_cache"
mkdir -p "$HF_HOME"

# Install requirements for model export
pip3 install -r https://raw.githubusercontent.com/openvinotoolkit/model_server/v2025.3/demos/common/export_models/requirements.txt


curl https://raw.githubusercontent.com/openvinotoolkit/model_server/v2025.3/demos/common/export_models/export_model.py -o export_model.py
mkdir -p "$VOLUME_OVMS/models"
python3 export_model.py text_generation --source_model $LLM_MODEL --weight-format $WEIGHT_FORMAT --config_file_path $VOLUME_OVMS/models/config.json --model_repository_path "$VOLUME_OVMS/models" --target_device $TARGET_DEVICE


# Wait for any process to exit
wait -n
