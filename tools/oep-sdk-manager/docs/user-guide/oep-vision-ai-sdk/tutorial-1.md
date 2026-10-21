# OEP Vision AI SDK - Tutorial 1

This tutorial demonstrates how to download AI models, set up the OpenVINO environment, and run performance benchmarks using Intel's optimized containers. You will learn to evaluate AI model performance across different hardware configurations including CPU, GPU, and Intel® Core™ Ultra processors.

## Overview

Performance benchmarking is crucial for understanding how AI models will perform in production environments. This tutorial uses the OpenVINO benchmark application to measure inference performance, helping you make informed decisions about hardware selection and model optimization.

## Time to Complete

**Estimated Duration:** 10-15 minutes

## Learning Objectives

Upon completion of this tutorial, you will be able to:

- Download and prepare AI models for benchmarking
- Configure OpenVINO benchmark environment using Docker containers
- Execute performance benchmarks on multiple hardware targets (CPU, GPU, NPU)
- Interpret benchmark results and performance metrics
- Understand the impact of different hardware configurations on AI inference

## Prerequisites

Before starting this tutorial, ensure you have:

- OEP Vision AI SDK installed and configured
- Docker installed and running on your system
- Basic familiarity with command-line operations
- Internet connection for downloading models and containers

## System Requirements

- **Operating System:** Ubuntu 22.04 LTS or Ubuntu 24.04 LTS
- **Memory:** Minimum 8GB RAM
- **Storage:** 5GB free disk space
- **Network:** Active internet connection

## Tutorial Steps

### Step 1: Create Working Directory and Download Assets

First, create a dedicated workspace and download the required video sample and AI model:

```bash
# Create working directory
mkdir -p ~/oep/oep-vision-tutorial-1
cd ~/oep/oep-vision-tutorial-1
```

### Step 2: Download Pre-trained Model

Download the YOLO11s model using the DL Streamer container:

```bash
# Download YOLO11s model using DL Streamer
docker run --rm --user=root \
  -e http_proxy -e https_proxy -e no_proxy \
  -v "${PWD}:/home/dlstreamer/" \
  intel/dlstreamer:2026.2.0-ubuntu24 \
  bash -c "export MODELS_PATH=/home/dlstreamer && /opt/intel/dlstreamer/samples/download_public_models.sh yolo11s"
```

This command will:

- Download the YOLO11s object detection model
- Convert it to OpenVINO IR format (FP16 precision)
- Store the model files in the `public/yolo11s/FP16/` directory

### Step 3: Run Benchmark on CPU

Execute the OpenVINO benchmark application to measure inference performance on CPU:

```bash
# Start the container
docker run -it --rm \
  --volume ${PWD}:/home/openvino \
  --env http_proxy=$http_proxy \
  --env https_proxy=$https_proxy \
  --env no_proxy=$no_proxy \
  openvino/ubuntu24_dev:2026.3.0
```

```bash
# Run the sample application
/opt/intel/openvino_2026.3.0.0/samples/cpp/samples_bin/samples_bin/benchmark_app \
-m /home/openvino/public/yolo11s/FP16/yolo11s.xml \
-data_shape "x[1,3,640,640]" \
-d CPU
```

```bash
# To exit the container
exit
```

![Benchamark Result](images/intel-edge-ai-box-sample-benchmark-output.png)

### Step 4: Run Benchmark on GPU (Optional)

If your system has Intel integrated graphics, run the benchmark on GPU for comparison:

```bash
docker run -it --rm \
  --volume ${PWD}:/home/openvino \
  --device /dev/dri:/dev/dri \
  --env http_proxy=$http_proxy \
  --env https_proxy=$https_proxy \
  --env no_proxy=$no_proxy \
  --user=root \
  openvino/ubuntu24_dev:2026.3.0 \
  /opt/intel/openvino_2026.3.0.0/samples/cpp/samples_bin/samples_bin/benchmark_app \
  -m /home/openvino/public/yolo11s/FP16/yolo11s.xml \
  -shape "[1,3,640,640]" \
  -d GPU
```

### Step 5: Run Benchmark on NPU (Intel® Core™ Ultra Processors)

```bash
docker run -it --rm \
  --volume ${PWD}:/home/openvino \
  --device=/dev/accel \
  --env http_proxy=$http_proxy \
  --env https_proxy=$https_proxy \
  --env no_proxy=$no_proxy \
  --user=root \
  openvino/ubuntu24_dev:2026.3.0 \
  /opt/intel/openvino_2026.3.0.0/samples/cpp/samples_bin/samples_bin/benchmark_app \
  -m /home/openvino/public/yolo11s/FP16/yolo11s.xml \
  -shape "[1,3,640,640]" \
  -d NPU
```

## Troubleshooting

### GPU Benchmark Fails

If the GPU benchmark fails (for example, the GPU device is not detected or inference errors occur), the container may be missing the Intel GPU compute runtime drivers. Install a compatible version of the drivers inside the container to resolve the issue.

Start the container in interactive mode:

```bash
docker run -it --rm \
  --volume ${PWD}:/home/openvino \
  --device /dev/dri:/dev/dri \
  --env http_proxy=$http_proxy \
  --env https_proxy=$https_proxy \
  --env no_proxy=$no_proxy \
  --user=root \
  openvino/ubuntu24_dev:2026.3.0
```

Update the package list and install `wget`:

```bash
apt-get update -y && apt-get install -y wget
```

Download and install the Intel GPU compute runtime drivers:

```bash
mkdir neo && \
  cd neo && \
  wget https://github.com/intel/intel-graphics-compiler/releases/download/v2.38.2/intel-igc-core-2_2.38.2+22051_amd64.deb && \
  wget https://github.com/intel/intel-graphics-compiler/releases/download/v2.38.2/intel-igc-opencl-2_2.38.2+22051_amd64.deb && \
  wget https://github.com/intel/compute-runtime/releases/download/26.27.39122.11/intel-ocloc-dbgsym_26.27.39122.11-0_amd64.ddeb && \
  wget https://github.com/intel/compute-runtime/releases/download/26.27.39122.11/intel-ocloc_26.27.39122.11-0_amd64.deb && \
  wget https://github.com/intel/compute-runtime/releases/download/26.27.39122.11/intel-opencl-icd-dbgsym_26.27.39122.11-0_amd64.ddeb && \
  wget https://github.com/intel/compute-runtime/releases/download/26.27.39122.11/intel-opencl-icd_26.27.39122.11-0_amd64.deb && \
  wget https://github.com/intel/compute-runtime/releases/download/26.27.39122.11/libigdgmm12_22.10.0_amd64.deb && \
  wget https://github.com/intel/compute-runtime/releases/download/26.27.39122.11/libze-intel-gpu1-dbgsym_26.27.39122.11-0_amd64.ddeb && \
  wget https://github.com/intel/compute-runtime/releases/download/26.27.39122.11/libze-intel-gpu1_26.27.39122.11-0_amd64.deb && \
  dpkg -i *.deb || apt-get install -f -y
```

Re-run the GPU benchmark:

```bash
/opt/intel/openvino_2026.3.0.0/samples/cpp/samples_bin/samples_bin/benchmark_app \
  -m /home/openvino/public/yolo11s/FP16/yolo11s.xml \
  -shape "[1,3,640,640]" \
  -d GPU
```

