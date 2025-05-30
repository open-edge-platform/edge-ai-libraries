#/bin/bash

set -euxo pipefail

# Create output directory
mkdir -p /output/pipeline-zoo-models

# Download pipeline zoo models repo if not already done
[ -d pipeline-zoo-models ] || \
    git clone --depth 1 --single-branch --branch main \
        https://github.com/dlstreamer/pipeline-zoo-models.git

# Define the pipeline zoo models to copy
pipeline_zoo_models=(
    efficientnet-b0_INT8
    ssdlite_mobilenet_v2_INT8
    resnet-50-tf_INT8
    yolov5m-416_INT8
    yolov5s-416_INT8
    yolov5m-640_INT8
)

# Copy the specified models to the output directory
for model in "${pipeline_zoo_models[@]}"; do
    [ -d "/output/pipeline-zoo-models/$model" ] ||
    cp -r "pipeline-zoo-models/storage/$model" /output/pipeline-zoo-models/
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
    [ -d "/output/public/$model" ] ||
    bash /opt/intel/dlstreamer/samples/download_public_models.sh "$model"
done
