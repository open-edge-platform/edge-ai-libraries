# OEP Vision AI SDK - Tutorial 4

This tutorial demonstrates how to build sophisticated video analytics pipelines using Intel® DL Streamer framework. You will learn to create real-time human pose estimation applications, understand GStreamer pipeline architecture, and develop custom video analytics solutions for computer vision applications.

## Overview

Intel® DL Streamer is a comprehensive video analytics framework built on GStreamer technology that enables rapid development of AI-powered video processing applications. This tutorial focuses on human pose estimation, a critical computer vision task used in sports analysis, healthcare monitoring, security systems, and human-computer interaction applications.

Human pose estimation involves detecting and tracking key points on the human body (joints, limbs) to understand body posture and movement patterns. This technology enables applications like fitness tracking, ergonomic analysis, action recognition, and assistive technologies.

## Time to Complete

**Estimated Duration:** 25-30 minutes

## Learning Objectives

Upon completion of this tutorial, you will be able to:

- Build advanced video analytics pipelines using Intel® DL Streamer framework
- Implement real-time human pose estimation with OpenVINO optimization
- Understand GStreamer plugin architecture and pipeline development
- Create custom video processing workflows for computer vision applications
- Optimize performance for real-time video analytics on Intel hardware
- Deploy containerized video analytics solutions
- Integrate multiple AI models in video processing pipelines
- Develop production-ready video analytics applications

## Prerequisites

Before starting this tutorial, ensure you have:

- OEP Vision AI SDK installed and configured
- Docker installed and running on your system
- Understanding of computer vision and AI inference concepts
- Basic familiarity with GStreamer framework
- X11 display server configured for GUI applications
- Internet connection for downloading models and video content

## System Requirements

- **Operating System:** Ubuntu 22.04 LTS or Ubuntu 24.04 LTS (Desktop edition required)
- **Processor:** Intel® Core™, Intel® Core™ Ultra
- **Memory:** Minimum 8GB RAM (16GB recommended for complex pipelines)
- **Storage:** 4GB free disk space for models, videos, and intermediate files
- **Graphics:** Intel integrated graphics (required for acceleration)
- **Display:** Monitor capable of displaying real-time video output

**Important Display Requirements**
This tutorial requires **Ubuntu Desktop** with a physical display and active graphical session. It will **not work** with:

- Ubuntu Server (no GUI)
- Remote SSH sessions without X11 forwarding
- Headless systems

You must be logged in to a local desktop session with a connected monitor or Remote Desktop/VNC connection for the video output to display correctly.

## Tutorial Steps

### Step 1: Create Working Directory and Download Assets

Set up your workspace and download the required video content and AI models:

```bash
# Create working directory structure
mkdir -p ~/oep/oep-vision-tutorial-4/{models,output}
cd ~/oep/oep-vision-tutorial-4

# Download sample video for human pose estimation
wget -O face-demographics-walking.mp4 \
  "https://github.com/intel-iot-devkit/sample-videos/raw/master/face-demographics-walking.mp4"

# Download and convert the YOLO26s-pose model to OpenVINO IR (FP16)
# using the model download script shipped in the DL Streamer container
docker run --rm --net=host \
  -e no_proxy=$no_proxy \
  -e https_proxy=$https_proxy \
  -e http_proxy=$http_proxy \
  -v ${PWD}:/home/dlstreamer/data \
  intel/dlstreamer:2026.2.0-ubuntu24 \
  bash -c "export MODELS_PATH=/home/dlstreamer/data/models && \
           /opt/intel/dlstreamer/samples/download_public_models.sh yolo26s-pose"
```

The model is saved to `models/public/yolo26s-pose/FP16/yolo26s-pose.xml`, which is the path expected by the DL Streamer human pose estimation sample.

### Step 2: Understand Human Pose Estimation Model

**Model Architecture:**

- **Model Name**: yolo26s-pose
- **Framework**: Ultralytics YOLO26 pose model converted to OpenVINO IR
- **Input**: 640x640 RGB image
- **Output**: Person bounding boxes with 17 COCO keypoints representing major body joints
- **Precision**: FP16

### Step 3: Configure Environment for DL Streamer

Prepare the environment for containerized video analytics:

```bash
# Enable X11 forwarding for GUI applications
xhost +local:docker

# Verify Docker access to display
echo "Display: $DISPLAY"
echo "X11 Auth: $HOME/.Xauthority"
```

### Step 4: Run Basic Human Pose Estimation Pipeline

Execute the pre-built human pose estimation pipeline using DL Streamer:

```bash
export RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')
# Run human pose estimation with DL Streamer container
docker run -it --rm --net=host \
  -e DISPLAY=$DISPLAY \
  -e no_proxy=$no_proxy \
  -e https_proxy=$https_proxy \
  -e http_proxy=$http_proxy \
  -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
  -v ${PWD}:/home/dlstreamer/data \
  -v $HOME/.Xauthority:/home/dlstreamer/.Xauthority:ro \
  --group-add $RENDER_GROUP_ID \
  --device=/dev/dri \
  intel/dlstreamer:2026.2.0-ubuntu24 \
  bash -c "export MODELS_PATH=/home/dlstreamer/data/models && \
           /opt/intel/dlstreamer/samples/gstreamer/gst_launch/human_pose_estimation/human_pose_estimation.sh \
           /home/dlstreamer/data/face-demographics-walking.mp4"
```

**Pipeline Execution Features:**

- Real-time human pose detection and visualization
- Skeletal overlay on detected persons
- Keypoint confidence scoring
- Multi-person pose estimation support
- Hardware-accelerated inference using OpenVINO

![Human Pose Estimation](./images/tutorial_dlstreamer_container.png)
