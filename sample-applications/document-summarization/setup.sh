#!/bin/bash

# Setup the OVMS configuration
export WEIGHT_FORMAT=int8
export TARGET_DEVICE=CPU

# Setup no_proxy
export no_proxy=${no_proxy},ovms-service,docsum-api,docsum-ui,localhost

# Setup OpenTelemetry and OpenLit Configurations 
export OTEL_SERVICE_NAME=document-summarization
export OTEL_SERVICE_ENV=development
export OTEL_SERVICE_VERSION=1.0.0 

if [ ! -e "$VOLUME_OVMS/models/$LLM_MODEL/config.json" ]; then
  docker run --rm -e http_proxy -e https_proxy -e no_proxy -e LLM_MODEL -e VOLUME_OVMS -e HF_TOKEN \
    -v "$(pwd):$(pwd)" -w "$(pwd)" -i ubuntu:24.04 bash <<EOF
apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y python3-venv git curl

# Create venv if it doesn't exist
python3 -m venv /venv

# Activate the virtual environment
source /venv/bin/activate

# Set Hugging Face cache directory to a local, writable path
export HF_HOME="/.hf_cache"

# Install requirements for model export
pip3 install -r https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/heads/releases/2025/1/demos/common/export_models/requirements.txt

curl https://raw.githubusercontent.com/openvinotoolkit/model_server/refs/heads/releases/2025/1/demos/common/export_models/export_model.py -o export_model.py
mkdir -p "$VOLUME_OVMS/models"
python3 export_model.py text_generation --source_model $LLM_MODEL --weight-format $WEIGHT_FORMAT --config_file_path $VOLUME_OVMS/models/config.json --model_repository_path "$VOLUME_OVMS/models" --target_device $TARGET_DEVICE

# Fix owner permission
chown -R $(id -u):$(id -g) "$VOLUME_OVMS/models"
EOF
fi

cat > .env <<EOF
VOLUME_OVMS=$VOLUME_OVMS
RELEASE=$RELEASE
TAG=$TAG
LLM_MODEL=$LLM_MODEL
WEIGHT_FORMAT=$WEIGHT_FORMAT
TARGET_DEVICE=$TARGET_DEVICE
no_proxy=$no_proxy
OTEL_SERVICE_NAME=$OTEL_SERVICE_NAME
OTEL_SERVICE_ENV=$OTEL_SERVICE_ENV
OTEL_SERVICE_VERSION=$OTEL_SERVICE_VERSION
EOF

