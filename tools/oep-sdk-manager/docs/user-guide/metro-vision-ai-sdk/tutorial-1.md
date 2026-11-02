<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Metro Vision AI SDK - Tutorial 1

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

- Metro Vision AI SDK installed and configured
- Docker installed and running on your system
- Basic familiarity with command-line operations
- Internet connection for downloading models and containers

## System Requirements

- **Operating System:** Ubuntu 24.04 LTS or Ubuntu 26.04 LTS
- **Memory:** Minimum 8GB RAM
- **Storage:** 5GB free disk space
- **Network:** Active internet connection

## Tutorial Steps

### Step 1: Create Working Directory and Download Assets

First, create a dedicated workspace and download the required video sample and AI model:

```bash
# Create working directory
mkdir -p ~/oep/metro-vision-tutorial-1
cd ~/oep/metro-vision-tutorial-1
```

### Step 2: Download Pre-trained Model

Download the YOLO11s model using the DL Streamer container:

Run all Docker commands as your regular non-root host user, without `sudo`.
Matching the container UID:GID to your host identity keeps generated files editable on the host.
The mounted workspace supplies a writable home for model preparation environments and caches.
Previously created root-owned files are not repaired by these commands; use a new user-owned workspace if necessary.

```bash
# Download YOLO11s model using DL Streamer
docker run --rm --user "$(id -u):$(id -g)" \
  -e HOME=/home/dlstreamer \
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
  --user "$(id -u):$(id -g)" \
  --env HOME=/home/openvino \
  --workdir /home/openvino \
  --volume "${PWD}:/home/openvino" \
  --env http_proxy=$http_proxy \
  --env https_proxy=$https_proxy \
  --env no_proxy=$no_proxy \
  openvino/ubuntu24_dev:2026.4.0
```

```bash
# Run the sample application
/opt/intel/openvino_2026.4.0.0/samples/cpp/samples_bin/samples_bin/benchmark_app \
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
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --env HOME=/tmp \
  --workdir /tmp \
  --volume "${PWD}/public:/models:ro" \
  --device /dev/dri:/dev/dri \
  --group-add "$(stat -c '%g' /dev/dri/renderD128)" \
  --env http_proxy \
  --env https_proxy \
  --env no_proxy \
  openvino/ubuntu24_dev:2026.4.0 \
  /opt/intel/openvino_2026.4.0.0/samples/cpp/samples_bin/samples_bin/benchmark_app \
  -m /models/yolo11s/FP16/yolo11s.xml \
  -shape "[1,3,640,640]" \
  -d GPU
```

### Step 5: Run Benchmark on NPU (Intel® Core™ Ultra Processors)

Verify that `/dev/accel/accel0` exists; substitute your NPU's device node if it differs.

```bash
docker run -it --rm \
  --user "$(id -u):$(id -g)" \
  --env HOME=/home/openvino \
  --workdir /home/openvino \
  --volume "${PWD}:/home/openvino" \
  --device=/dev/accel \
  --group-add "$(stat -c '%g' /dev/accel/accel0)" \
  --env http_proxy=$http_proxy \
  --env https_proxy=$https_proxy \
  --env no_proxy=$no_proxy \
  openvino/ubuntu24_dev:2026.4.0 \
  /opt/intel/openvino_2026.4.0.0/samples/cpp/samples_bin/samples_bin/benchmark_app \
  -m /home/openvino/public/yolo11s/FP16/yolo11s.xml \
  -shape "[1,3,640,640]" \
  -d NPU
```
