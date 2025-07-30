#/bin/bash

set -euo pipefail

# Remove healthcheck.txt if it exists
rm -f healthcheck.txt

# Create output directory
mkdir -p /output/pipeline-zoo-models

# Define the pipeline zoo models to copy
pipeline_zoo_models=(
    efficientnet-b0_INT8
    ssdlite_mobilenet_v2_INT8
    resnet-50-tf_INT8
    yolov5m-416_INT8
    yolov5s-416_INT8
    yolov5m-640_INT8
)

# Copy the specified models to the output directory, cloning the repo only if needed
for model in "${pipeline_zoo_models[@]}"; do
    if [ ! -d "/output/pipeline-zoo-models/$model" ]; then
        if [ ! -d pipeline-zoo-models-main ]; then
            curl -L https://github.com/dlstreamer/pipeline-zoo-models/archive/refs/heads/main.tar.gz -o pipeline-zoo-models.tar.gz
            tar -xvzf pipeline-zoo-models.tar.gz
            rm pipeline-zoo-models.tar.gz
        fi
        cp -r "pipeline-zoo-models-main/storage/$model" /output/pipeline-zoo-models/
    else
        echo "Model $model already exists. Skipping download."
    fi
done

download_public_models=(
    yolov10s
    yolov10m
)

for model in "${download_public_models[@]}"; do
    if [ ! -d "/output/public/$model" ]; then
        bash /opt/intel/dlstreamer/samples/download_public_models.sh "$model"
    fi
done

# Set the name of the virtual environment directory
VENV_DIR="$HOME/.venv"

create_virtual_env() {
    # Create a Python virtual environment if it doesn't exist
    if [ ! -d "$VENV_DIR" ]; then
        echo "Creating virtual environment in $VENV_DIR..."
        python3 -m venv "$VENV_DIR"
    fi

    # Activate the virtual environment
    echo "Activating virtual environment in $VENV_DIR..."
    source "$VENV_DIR/bin/activate"
}

delete_virtual_env() {
    # Deactivate and remove venvs
    echo "Removing Python virtual environment..."
    if [ -n "$VIRTUAL_ENV" ]; then
        deactivate
    fi
    rm -rf $VENV_DIR
    echo "Removed"
}

# TEMPORARY: download mobilenet-v2-pytorch until the download script supports it
if [ ! -d /output/public/mobilenet-v2-pytorch ]; then
    create_virtual_env
    pip install openvino-dev[onnx] torch torchvision \
        --extra-index-url https://download.pytorch.org/whl/cpu
    omz_downloader --name mobilenet-v2-pytorch
    omz_converter --name mobilenet-v2-pytorch
    cp -r ./public/mobilenet-v2-pytorch /output/public/
    cp /opt/intel/dlstreamer/samples/gstreamer/model_proc/public/preproc-aspect-ratio.json \
       /output/public/mobilenet-v2-pytorch/mobilenet-v2.json
    python3 -c "
import json
labels_path = '/opt/intel/dlstreamer/samples/labels/imagenet_2012.txt'
json_path = '/output/public/mobilenet-v2-pytorch/mobilenet-v2.json'
labels = []
with open(labels_path, 'r') as f:
    for line in f:
        parts = line.strip().split(' ', 1)
        if len(parts) == 2:
            labels.append(parts[1])
        else:
            labels.append(parts[0])
with open(json_path, 'r') as f:
    data = json.load(f)
if 'output_postproc' in data and isinstance(data['output_postproc'], list) and data['output_postproc']:
    data['output_postproc'][0]['labels'] = labels
with open(json_path, 'w') as f:
    json.dump(data, f, indent=4)
"
    delete_virtual_env
fi

# Create the healthcheck file
touch healthcheck.txt
