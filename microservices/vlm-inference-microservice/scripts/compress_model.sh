#!/bin/bash

VLM_MODEL_NAME=$1
VLM_COMPRESSION_WEIGHT_FORMAT=$2

MODEL_DIR=$(echo $VLM_MODEL_NAME | awk -F/ '{print $NF}')
MODEL_DIR="ov-model/$MODEL_DIR/$VLM_COMPRESSION_WEIGHT_FORMAT"

echo "Model Name: $VLM_MODEL_NAME"
echo "Compression Weight Format: $VLM_COMPRESSION_WEIGHT_FORMAT"
echo "Model Directory: $MODEL_DIR"

if [ ! -d "$MODEL_DIR" ]; then
    echo "Model directory does not exist. Exporting model..."
    echo "Starting model compression..."
    optimum-cli export openvino --trust-remote-code --model $VLM_MODEL_NAME $MODEL_DIR --weight-format $VLM_COMPRESSION_WEIGHT_FORMAT
    echo "Model exported successfully to $MODEL_DIR"
else
    echo "Model directory already exists. Skipping export."
fi

echo "Model compression script completed."