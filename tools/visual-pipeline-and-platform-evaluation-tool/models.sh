#!/bin/bash

set -euo pipefail

DOWNLOAD_PUBLIC_MODELS=${DOWNLOAD_PUBLIC_MODELS:-false}

main() {
    echo "Starting model setup at $(date)"

    download_pipeline_zoo_models
    download_public_models
    download_open_model_zoo

    echo "Model setup completed at $(date)"
}

download_pipeline_zoo_models() {
    # Create output directory
    mkdir -p /output/pipeline-zoo-models

    # Define the pipeline zoo models to copy
    pipeline_zoo_models=(
        efficientnet-b0_INT8
        ssdlite_mobilenet_v2_INT8
        resnet-50-tf_INT8
        yolov5m-416_INT8
        yolov5s-416_INT8
    )

    extra_models=(
        yolov5m-640_INT8
    )

    if [[ "${DOWNLOAD_PUBLIC_MODELS}" == "true" ]]; then
        pipeline_zoo_models+=("${extra_models[@]}")
    else
        echo "DOWNLOAD_PUBLIC_MODELS is not true. Skipping download of: ${extra_models[*]}"
    fi

    # Copy the specified models to the output directory, cloning the repo only if needed
    for model in "${pipeline_zoo_models[@]}"; do
        if [ ! -d "/output/pipeline-zoo-models/$model" ]; then
            if [ ! -d pipeline-zoo-models-main ]; then
                curl -L https://github.com/dlstreamer/pipeline-zoo-models/archive/refs/heads/main.tar.gz -o pipeline-zoo-models.tar.gz
                tar -xzf pipeline-zoo-models.tar.gz
                rm pipeline-zoo-models.tar.gz
            fi
            cp -r "pipeline-zoo-models-main/storage/$model" /output/pipeline-zoo-models/
        else
            echo "Model $model already exists. Skipping download."
        fi
    done
}

download_public_models() {
    models=(
        yolov8_license_plate_detector
        ch_PP-OCRv4_rec_infer
    )
    extra_models=(
        yolov10s
        yolov10m
    )

    if [[ "${DOWNLOAD_PUBLIC_MODELS}" == "true" ]]; then
        models+=("${extra_models[@]}")
    else
        echo "DOWNLOAD_PUBLIC_MODELS is not true. Skipping download of: ${extra_models[*]}"
    fi

    for model in "${models[@]}"; do
        if [ ! -d "/output/public/$model" ]; then
            bash /opt/intel/dlstreamer/samples/download_public_models.sh "$model"
        else
            echo "Model $model already exists. Skipping download."
        fi
    done
}

download_open_model_zoo() {
    if [ ! -d /output/public/mobilenet-v2-pytorch ] || \
       [ ! -d /output/intel/vehicle-attributes-recognition-barrier-0039 ]; then
        VENV_DIR="$HOME/.venv"
        python3 -m venv "$VENV_DIR"
        source "$VENV_DIR/bin/activate"

        pip install openvino-dev[onnx] torch torchvision \
            --extra-index-url https://download.pytorch.org/whl/cpu
    fi

    # TEMPORARY: download mobilenet-v2-pytorch until the download script supports it
    if [[ ! -d /output/public/mobilenet-v2-pytorch && "${DOWNLOAD_PUBLIC_MODELS}" == "true" ]]; then
        omz_downloader --name mobilenet-v2-pytorch --output_dir /output
        omz_converter --name mobilenet-v2-pytorch --output_dir /output --download_dir /output
        cp \
            /opt/intel/dlstreamer/samples/gstreamer/model_proc/public/preproc-aspect-ratio.json \
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
    elif [[ "${DOWNLOAD_PUBLIC_MODELS}" != "true" ]]; then
        echo "DOWNLOAD_PUBLIC_MODELS is not true. Skipping download of: mobilenet-v2-pytorch"
    else
        echo "Model mobilenet-v2-pytorch already exists. Skipping download."
    fi

    # TEMPORARY: download vehicle-attributes-recognition-barrier-0039 until the download script supports it
    if [ ! -d /output/intel/vehicle-attributes-recognition-barrier-0039 ]; then
        omz_downloader --name vehicle-attributes-recognition-barrier-0039 --output_dir /output
        omz_converter --name vehicle-attributes-recognition-barrier-0039 --output_dir /output \
            --download_dir /output
        cp \
            /opt/intel/dlstreamer/samples/gstreamer/model_proc/intel/vehicle-attributes-recognition-barrier-0039.json \
            /output/intel/vehicle-attributes-recognition-barrier-0039/vehicle-attributes-recognition-barrier-0039.json
    else
        echo "Model vehicle-attributes-recognition-barrier-0039 already exists. Skipping download."
    fi
}

main
