#/bin/bash

set -euxo pipefail

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
        if [ ! -d pipeline-zoo-models ]; then
            git clone --depth 1 --single-branch --branch main \
                https://github.com/dlstreamer/pipeline-zoo-models.git
        fi
        cp -r "pipeline-zoo-models/storage/$model" /output/pipeline-zoo-models/
    fi
done

# TEMPORARY: modify the download script to use CPU wheels for ultralytics
sed -i \
    's|pip install ultralytics --upgrade|pip install ultralytics --upgrade --extra-index-url https://download.pytorch.org/whl/cpu|' \
    /opt/intel/dlstreamer/samples/download_public_models.sh

# Define the models to download using the modified script
download_public_models=(
    yolov10s
    yolov10m
)

# Download the specified models using the modified script
for model in "${download_public_models[@]}"; do
    if [ ! -d "/output/public/$model" ]; then
        bash /opt/intel/dlstreamer/samples/download_public_models.sh "$model"
    fi
done

# TEMPORARY: download mobilenet-v2-pytorch until the download script supports it
if [ ! -d /output/public/mobilenet-v2-pytorch ]; then
    python3 -m pip install openvino-dev[onnx] torch torchvision \
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
fi

# Create the healthcheck file
touch healthcheck.txt
