# OEP Vision AI SDK - Tutorial 5

This tutorial will guide you through profiling and monitoring performance of OEP Vision AI workloads using command-line tools. You'll learn to use `htop` and `intel_gpu_top` (or `gputop` on newer platforms) to analyze system performance while running DL Streamer Pipeline Server or OpenVINO applications.

## Prerequisites

- Ubuntu 22.04 or later
- Docker installed and configured
- Intel® Core™, Intel® Core™ Ultra and Intel integrated graphics card
- Administrative privileges for performance monitoring
- Internet connection for downloading model and video files

## Step 1: Install Performance Monitoring Tools

Install the required command-line performance monitoring tools:

```bash
# Update system packages
sudo apt update

# Install performance monitoring tools
sudo apt install -y htop intel-gpu-tools

# Verify installations
htop --version
intel_gpu_top --help
```

### Newer platforms using the `xe` kernel driver (Panther Lake, Wildcat Lake, Lunar Lake, Battlemage)

Check which kernel driver your GPU uses:

```bash
lspci -k | grep -A3 -Ei "vga|display" | grep "Kernel driver"
```

If it reports `xe`, the `intel-gpu-tools` package from Ubuntu (1.28 on Ubuntu 24.04) cannot detect the GPU and `intel_gpu_top` fails with:

```text
No device filter specified and no discrete/integrated i915 devices found
```

Upstream `intel_gpu_top` supports only `i915` devices. For `xe` devices, use the `gputop` tool. To get it, build a recent IGT GPU Tools release from source:

```bash
sudo apt install -y git meson ninja-build pkg-config build-essential flex bison \
  libdrm-dev libkmod-dev libproc2-dev libdw-dev libpciaccess-dev libpci-dev libudev-dev \
  libcairo2-dev libpixman-1-dev libssl-dev libjson-c-dev libunwind-dev \
  libxmlrpc-core-c3-dev liblzma-dev libgsl-dev libasound2-dev python3-docutils

git clone --depth 1 --branch v2.6 https://gitlab.freedesktop.org/drm/igt-gpu-tools.git ~/igt-gpu-tools
cd ~/igt-gpu-tools
meson setup build -Dtests=disabled -Dman=disabled -Ddocs=disabled -Drunner=disabled
ninja -C build
sudo ninja -C build install
sudo ldconfig

# Verify: the GPU should now be listed (for example "Intel Wildcatlake (Gen30)")
sudo intel_gpu_top -L
gputop -h
```

## Step 2: Verify System Hardware

Check your system hardware for monitoring:

```bash
# Check CPU information
lscpu | grep -E "Model name|CPU\(s\)"

# Check GPU availability
lspci | grep -i vga

# Check Intel GPU device files
ls -la /dev/dri/
```

## Step 3: Start Your OEP Vision AI Workload

Create and start a DL Streamer pipeline that continuously runs in the background for profiling:

```bash
mkdir -p ~/oep/oep-vision-tutorial-5
cd ~/oep/oep-vision-tutorial-5

# Download sample video for object detection
wget -O bottle-detection.mp4 https://storage.openvinotoolkit.org/test_data/videos/bottle-detection.mp4

# Download YOLOv10s model using DL Streamer container
docker run --rm --user=root \
  -e http_proxy -e https_proxy -e no_proxy \
  -v "${PWD}:/home/dlstreamer/" \
  intel/dlstreamer:2026.2.0-ubuntu24 \
  bash -c "export MODELS_PATH=/home/dlstreamer && /opt/intel/dlstreamer/samples/download_public_models.sh yolov10s"

# Create a continuous DL Streamer pipeline script
cat > oep_vision_pipeline.sh << 'EOF'
#!/bin/bash

# OEP Vision AI DL Streamer Pipeline for Performance Testing using Docker
CURRENT_DIR=$(pwd)
MODEL_PATH="$CURRENT_DIR/public/yolov10s/FP32/yolov10s.xml"
VIDEO_PATH="$CURRENT_DIR/bottle-detection.mp4"
DEVICE=GPU
RENDER_GROUP_ID=$(getent group render | awk -F: '{printf "%s\n", $3}')


echo "Starting OEP Vision AI Pipeline with Docker DL Streamer..."
echo "Model: $MODEL_PATH"
echo "Video: $VIDEO_PATH"
echo "Device: $DEVICE"

# Check if model and video exist
if [[ ! -f "$MODEL_PATH" ]]; then
    echo "Error: Model file not found at $MODEL_PATH"
    exit 1
fi

if [[ ! -f "$VIDEO_PATH" ]]; then
    echo "Error: Video file not found at $VIDEO_PATH"
    exit 1
fi


# Continuous loop to keep pipeline running
while true; do
    echo "$(date): Starting pipeline iteration..."

    # Run DL Streamer pipeline in Docker container with object detection
    docker run --rm \
        --device /dev/dri:/dev/dri \
        --group-add $RENDER_GROUP_ID \
        -v "$CURRENT_DIR:/workspace" \
        -v $HOME/.Xauthority:/root/.Xauthority:rw \
        -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
        --env DISPLAY=$DISPLAY \
        --env http_proxy=$http_proxy \
        --env https_proxy=$https_proxy \
        --env no_proxy=$no_proxy \
        --user root \
        -w /workspace \
        intel/dlstreamer:2026.2.0-ubuntu24  \
        gst-launch-1.0 \
            filesrc location=/workspace/bottle-detection.mp4 ! \
            qtdemux ! h264parse ! avdec_h264 ! \
            videoconvert ! \
            gvadetect model=/workspace/public/yolov10s/FP32/yolov10s.xml device="$DEVICE" ! \
            gvafpscounter ! \
            fakesink sync=false \
            2>/dev/null

    echo "$(date): Pipeline ended, restarting in 2 seconds..."
    sleep 2
done
EOF

chmod +x oep_vision_pipeline.sh

# Start the pipeline in background
sudo ./oep_vision_pipeline.sh &
PIPELINE_PID=$!

echo "OEP Vision AI pipeline started with PID: $PIPELINE_PID"
echo "Use 'kill $PIPELINE_PID' to stop the pipeline when done profiling"
```

> [!NOTE]
> This creates a continuously running Docker-based DL Streamer pipeline that processes real video using the YOLOv10s object detection model, providing a realistic AI workload for performance profiling. The pipeline runs in a Docker container with access to Intel GPU hardware.

**Expected Console Output:**

![Tutorial 5 Output](./images/tutorial-5-dlstreamer-output.png)

## Step 4: Monitor Overall System Performance with htop

Launch htop to monitor real-time system performance:

```bash
# Start htop for real-time monitoring
htop
```

**What to observe:**

- CPU usage per core (bars at the top)
- Memory usage and available memory
- Running processes sorted by CPU usage
- Look for your OEP Vision AI processes

**Key shortcuts in htop:**

- `F6` - Sort by different columns (CPU%, MEM%)
- `F4` - Filter processes by name
- `q` - Quit htop

**Expected Console Output:**

![Tutorial 5 Top Output](./images/tutorial-5-top.png)

## Step 5: Monitor Intel GPU Performance

Use `intel_gpu_top` to monitor GPU usage during AI inference:

```bash
# Start Intel GPU monitoring
sudo intel_gpu_top
```

**What to observe:**

- Render/3D engine usage (shows AI inference workload)
- Video engine usage (shows video decode/encode)
- GPU frequency and power consumption
- Memory usage and bandwidth

**Expected Console Output:**

![Tutorial 5 GPU Top Output](./images/tutorial-5-gpu-top.png)

### On `xe` driver platforms (Panther Lake, Wildcat Lake)

`intel_gpu_top` reports `Detected Xe device which is not supported by intel_gpu_top`. Use `gputop` instead:

```bash
sudo gputop
```

`gputop` shows per-process GPU memory and engine utilization for each DRM device:

```text
DRM minor 128   Frequency(MHz) GT0-2600/2600 GT1-550/550
   PID      MEM      RSS     rcs        vcs       vecs        bcs        ccs     NAME
466292     158M     158M |  0.0%   ||  0.0%   ||  0.0%   ||  0.0%   || 49.6% █ | gst-launch-1.0
```

- `ccs` (compute) - OpenVINO GPU inference runs here on `xe` platforms
- `rcs` (render/3D), `vcs` (video decode/encode), `vecs` (video enhancement), `bcs` (copy)
- `vcs` stays at 0% in this tutorial because `avdec_h264` decodes on the CPU

## Step 6: Stop the Running Pipeline

When you are done profiling, stop the background pipeline:

```bash
# Stop the background DL Streamer pipeline
sudo pkill -9 -f oep_vision_pipeline.sh
```

## Next Steps: Visual Pipeline and Platform Evaluation Tool (ViPPET)

Now that you have learned to monitor AI workloads with command-line tools, take your performance analysis to the next level with **ViPPET** - a visual tool for evaluating and optimizing AI pipelines.

### What is ViPPET?

ViPPET (Visual Pipeline and Platform Evaluation Tool) is an interactive web-based application that helps you:

- **Visualize Pipeline Performance**: See real-time metrics and graphs of your AI pipeline performance
- **Compare Configurations**: Test different hardware devices (CPU, GPU, NPU) and model configurations
- **Benchmark Workloads**: Measure throughput, latency, and resource utilization
- **Optimize Pipelines**: Identify bottlenecks and tune parameters for better performance
- **Generate Reports**: Create detailed performance reports for analysis and documentation

### Getting Started with ViPPET

To learn more and get started with ViPPET, visit the official documentation:

**[ViPPET Documentation](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/visual-pipeline-and-platform-evaluation-tool/index.html)**

The documentation includes:

- Installation instructions
- Quick start guides
- Tutorial videos
- Pipeline configuration examples
- Performance tuning best practices

### Why Use ViPPET After This Tutorial?

After using `htop` and `intel_gpu_top` for basic monitoring, ViPPET provides:

1. **Visual Analysis**: Interactive charts instead of terminal output
2. **Automated Testing**: Run multiple benchmark scenarios automatically
3. **Comparative Analysis**: Side-by-side comparison of different configurations
4. **Historical Data**: Track performance trends over time
5. **Export Capabilities**: Generate professional reports for stakeholders

ViPPET complements the command-line monitoring skills you have learned in this tutorial by providing a comprehensive visual interface for deeper performance analysis and optimization.

## Summary

This tutorial provides a practical approach to profiling OEP Vision AI workloads using command-line tools:

### **What You have Learned:**

1. **Installing Tools**: Set up `htop` and `intel_gpu_top` for system monitoring
2. **System Monitoring**: Use `htop` for real-time CPU and memory monitoring
3. **GPU Profiling**: Monitor Intel GPU performance with `intel_gpu_top` (`i915`) or `gputop` (`xe`)
4. **Performance Analysis**: Understand resource utilization patterns

### **Key Monitoring Points:**

- **CPU Usage**: Monitor core utilization and identify bottlenecks
- **Memory Usage**: Track memory consumption and avoid swapping
- **GPU Utilization**: Monitor Intel GPU render engine usage
- **Process Performance**: Track specific AI application performance
