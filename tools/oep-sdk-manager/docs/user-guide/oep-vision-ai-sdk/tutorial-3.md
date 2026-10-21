# OEP Vision AI SDK - Tutorial 3

This tutorial demonstrates how to implement real-time object detection using YOLOv10s model with OpenVINO Runtime. You will learn to create a complete computer vision application that processes video streams, performs AI inference, and displays results with bounding boxes and confidence scores in real-time.

## Overview

Object detection is a fundamental computer vision task that identifies and localizes objects within images or video streams. This tutorial uses YOLOv10s (You Only Look Once version 10 small), a state-of-the-art object detection model optimized for real-time performance. You will build a complete application using OpenVINO Runtime for optimized inference on Intel hardware.

In this tutorial, you will analyze a city intersection video to detect vehicles, pedestrians, and traffic infrastructure in real-time. This practical example demonstrates how AI can be applied to traffic monitoring, urban planning, and smart city applications.

## Time to Complete

**Estimated Duration:** 20-25 minutes

## Learning Objectives

Upon completion of this tutorial, you will be able to:

- Deploy YOLOv10s object detection model using OpenVINO Runtime
- Implement real-time video processing with computer vision techniques
- Create custom Python applications for AI inference
- Understand object detection pipeline: preprocessing, inference, and postprocessing
- Optimize performance for real-time applications on Intel hardware
- Integrate bounding box visualization and confidence scoring
- Handle video input/output and user interaction

## Prerequisites

Before starting this tutorial, ensure you have:

- OEP Vision AI SDK installed and configured
- Docker installed and running on your system
- Python programming experience (intermediate level)
- Basic understanding of computer vision concepts
- X11 display server configured for GUI applications
- Internet connection for downloading models and video content

## System Requirements

- **Operating System:** Ubuntu 22.04 LTS or Ubuntu 24.04 LTS (Desktop edition required)
- **Processor:** Intel® Core™, Intel® Core™ Ultra, or Intel® Xeon® processors
- **Memory:** Minimum 8GB RAM (16GB recommended for optimal performance)
- **Storage:** 3GB free disk space for models and video files
- **Graphics:** Intel integrated graphics or discrete GPU (optional for acceleration)
- **Display:** Monitor capable of displaying video output

**Important Display Requirements**
This tutorial requires **Ubuntu Desktop** with a physical display and active graphical session. It will **not work** with:

- Ubuntu Server (no GUI)
- Remote SSH sessions without X11 forwarding
- Headless systems

You must be logged in to a local desktop session with a connected monitor or Remote Desktop/VNC connection for the video output to display correctly.

## Tutorial Steps

### Step 1: Create Working Directory

Set up your workspace and download a sample city intersection video

```bash
# Create working directory structure
mkdir -p ~/oep/oep-vision-tutorial-3
cd ~/oep/oep-vision-tutorial-3

# Download sample city intersection video for object detection
wget -O intersection.mp4 https://www.pexels.com/download/video/34505889?fps=29.97&h=360&w=640

```

This sample video shows a busy city intersection with vehicles, pedestrians, and traffic lights - ideal for demonstrating real-time object detection capabilities.

### Step 2: Download and Prepare YOLOv10s Model

Download the YOLOv10s object detection model and convert it to OpenVINO format:

```bash
# Download YOLOv10s model using DL Streamer container
docker run --rm --user=root \
  -e http_proxy -e https_proxy -e no_proxy \
  -v "${PWD}:/home/dlstreamer/" \
  intel/dlstreamer:2026.2.0-ubuntu24 \
  bash -c "export MODELS_PATH=/home/dlstreamer && /opt/intel/dlstreamer/samples/download_public_models.sh yolov10s"
```

**Model Download Process:**

1. Downloads YOLOv10s PyTorch model from official repository
2. Converts to OpenVINO Intermediate Representation (IR) format
3. Optimizes for Intel hardware acceleration
4. Saves model files in FP16 precision for optimal performance

### Step 3: Create Real-Time Object Detection Application

Create a comprehensive Python application for real-time object detection with advanced features:

```bash
# Create the main inference application
cat > inference.py << 'EOF'

import cv2
import numpy as np
from openvino import Core

# --- Configuration ---
model_path = "/home/openvino/public/yolov10s/FP16/yolov10s.xml"
video_path = "/home/openvino/intersection.mp4"
conf_threshold = 0.4
iou_threshold = 0.45


class_names = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train",
    "truck", "boat", "traffic light", "fire hydrant", "stop sign",
    "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag",
    "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon",
    "bowl", "banana", "apple", "sandwich", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "chair", "couch", "potted plant",
    "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush"
]

# --- Initialize OpenVINO Core and Load Model ---
ie = Core()
model = ie.read_model(model=model_path)

# Reshape model to static input shape if dynamic (YOLOv10s expects 640x640)
if model.inputs[0].partial_shape.is_dynamic:
    model.reshape({model.inputs[0].any_name: [1, 3, 640, 640]})

compiled_model = ie.compile_model(model=model, device_name="CPU")

# Get model input and output information
input_layer = compiled_model.inputs[0]
output_layer = compiled_model.outputs[0]

# Read input video
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    raise RuntimeError(f"Failed to open video: {video_path}")

# Get model input shape
_, _, h, w = input_layer.shape

# Define colors for bounding boxes
colors = np.random.uniform(0, 255, size=(100, 3))

def preprocess(frame):
    """Resize and normalize frame for YOLO input."""
    image = cv2.resize(frame, (w, h))
    image = image.transpose((2, 0, 1))  # HWC to CHW
    image = np.expand_dims(image, axis=0)
    image = image.astype(np.float32) / 255.0
    return image

def postprocess(frame, results):
    """Post-process YOLO output to draw boxes."""
    # YOLOv10 output shape: [1, 300, 6] where 6 = [x1, y1, x2, y2, conf, class_id]
    detections = np.squeeze(results)  # Remove batch dimension
    ih, iw, _ = frame.shape

    print(f"Detections shape: {detections.shape}")  # Debug info

    for det in detections:
        conf = det[4]
        if conf < conf_threshold:
            continue

        # YOLOv10 output: [x1, y1, x2, y2, conf, class_id]
        x1, y1, x2, y2 = det[:4]
        class_id = int(det[5])

        # Coordinates are normalized to input size (640x640)
        # Scale to original frame size
        x1 = int(x1 * iw / w)
        y1 = int(y1 * ih / h)
        x2 = int(x2 * iw / w)
        y2 = int(y2 * ih / h)

        # Ensure coordinates are within frame bounds
        x1 = max(0, min(x1, iw))
        y1 = max(0, min(y1, ih))
        x2 = max(0, min(x2, iw))
        y2 = max(0, min(y2, ih))

        color = colors[class_id % len(colors)]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness=3)
        label = class_names[class_id] if class_id < len(class_names) else f"ID:{class_id}"
        cv2.putText(frame, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.5, color, thickness=3)

        print(f"Detection: class={class_id}, conf={conf:.2f}, box=[{x1},{y1},{x2},{y2}]")  # Debug

    return frame

# --- Inference Loop ---
frame_count = 0
display_width, display_height = 960, 540  # Desired display size

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_count += 1
    input_image = preprocess(frame)  # Original frame for model
    results = compiled_model([input_image])
    detections = results[output_layer]

    frame = postprocess(frame, detections)

    # Resize frame for display
    frame_resized = cv2.resize(frame, (display_width, display_height))

    # Add frame counter
    cv2.putText(frame_resized, f"Frame: {frame_count}", (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    cv2.imshow("YOLOv10s OpenVINO Detection", frame_resized)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
EOF
```

### Step 4: Configure Environment and Execute Detection

Prepare the execution environment for GUI applications and run the object detection:

```bash
# Enable X11 forwarding for Docker containers
xhost +
```

### Step 5: Run Object Detection on CPU

Execute the real-time object detection application using OpenVINO on CPU:

```bash
# Run object detection with CPU inference
docker run -it --rm \
  --volume ${PWD}:/home/openvino \
  --volume $HOME/.Xauthority:/root/.Xauthority:rw \
  --volume /tmp/.X11-unix:/tmp/.X11-unix:rw \
  --env DISPLAY=$DISPLAY \
  --env http_proxy=$http_proxy \
  --env https_proxy=$https_proxy \
  --env no_proxy=$no_proxy \
  --user root \
  openvino/ubuntu24_dev:2026.2.0
```

```bash
apt update
apt install -y libgtk2.0-dev pkg-config libcanberra-gtk-module libcanberra-gtk3-module build-essential cmake git pkg-config libgtk2.0-dev libavcodec-dev libavformat-dev libswscale-dev libv4l-dev libxvidcore-dev libx264-dev libjpeg-dev libpng-dev libtiff-dev libdc1394-dev ffmpeg
pip install opencv-python "numpy<2"
```

```bash
python3 /home/openvino/inference.py
```

**Expected Console Output:**

![Tutorial 3 Output](./images/tutorial-3-output.png)

### Step 6: Run Object Detection on GPU (Optional)

For systems with Intel integrated graphics, run detection with GPU acceleration:

```bash
# Run object detection with GPU inference
docker run -it --rm \
  --volume ${PWD}:/home/openvino \
  --volume $HOME/.Xauthority:/root/.Xauthority:rw \
  --volume /tmp/.X11-unix:/tmp/.X11-unix:rw \
  --device /dev/dri \
  --env DISPLAY=$DISPLAY \
  --env http_proxy=$http_proxy \
  --env https_proxy=$https_proxy \
  --env no_proxy=$no_proxy \
  --user root \
  openvino/ubuntu24_dev:2026.2.0
```

```bash
apt update
apt install -y libgtk2.0-dev pkg-config libcanberra-gtk-module libcanberra-gtk3-module build-essential cmake git pkg-config libgtk2.0-dev libavcodec-dev libavformat-dev libswscale-dev libv4l-dev libxvidcore-dev libx264-dev libjpeg-dev libpng-dev libtiff-dev libdc1394-dev ffmpeg
pip install opencv-python "numpy<2"
```

```bash
python3 /home/openvino/inference.py
```

**Custom Thresholds:**

```bash
# High precision detection (lower false positives)
python3 /home/openvino/inference.py --conf 0.6 --iou 0.3

# High recall detection (catch more objects)
python3 /home/openvino/inference.py --conf 0.3 --iou 0.5
```

## Understanding the Application

### YOLOv10s Architecture

**Model Characteristics:**

- **Architecture**: Single-stage object detection network
- **Input Size**: 640x640 pixels
- **Output**: Bounding boxes with confidence scores for 80 COCO classes
- **Optimization**: FP16 precision for optimal performance on Intel hardware

**Detection Classes:**
The model can detect 80 different object classes from the COCO dataset. In the city intersection video, you will commonly see:

- **People**: person
- **Vehicles**: car, truck, bus, motorcycle, bicycle
- **Traffic Infrastructure**: traffic light, stop sign
- **Other Objects**: backpack, handbag, umbrella, and more

### Pipeline Architecture

**Processing Flow:**

1. **Input**: Video frame (BGR format from OpenCV)
2. **Preprocessing**: Resize → RGB conversion → Normalization → Tensor formatting
3. **Inference**: OpenVINO optimized neural network execution
4. **Postprocessing**: Coordinate conversion → Confidence filtering → Non-Maximum Suppression
5. **Visualization**: Bounding box drawing → Label annotation → Performance overlay
6. **Output**: Annotated frame display

**Key Components:**

- **OpenVINO Runtime**: Optimized inference engine for Intel hardware
- **YOLOv10s Model**: Pre-trained object detection neural network
- **OpenCV**: Computer vision library for image processing and display
- **NumPy**: Numerical computing for efficient array operations

### Performance Optimization Features

**Hardware Acceleration:**

- **CPU Optimization**: Vectorized operations using Intel® AVX instructions
- **GPU Acceleration**: Intel integrated graphics compute units
- **Memory Efficiency**: Optimized memory layout and minimal data copies

**Software Optimizations:**

- **FP16 Precision**: Reduced memory usage and faster computation
- **Batch Processing**: Single frame inference optimized for real-time performance
- **Pipeline Parallelism**: Overlapped preprocessing and inference operations
- **Efficient NMS**: Optimized Non-Maximum Suppression implementation
