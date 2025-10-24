# Install Guide Ubuntu 24.04 on WSL2

This page describes steps required to install Deep Learning Streamer Pipeline
Framework on Ubuntu, when hosted on a Windows machine using WSL2.

## On Windows Host System

### Step 1: Update the GPU drivers

Download and install the latest Intel® GPU drivers from
[intel-arc-iris-xe-graphics-windows](https://www.intel.com/content/www/us/en/download/785597/intel-arc-iris-xe-graphics-windows.html)

### Step 2: Install WSL

Open a PowerShell prompt as an Administrator and run

```bash
wsl --install
```

or

```bash
wsl --update
```

in case you have installed it before.

Visit
[install-ubuntu-wsl2](https://documentation.ubuntu.com/wsl/en/latest/howto/install-ubuntu-wsl2)
in case of any Ubuntu-WSL2 installation issues.

### Step 3: Install Ubuntu 24.04.1 LTS

Open a PowerShell prompt as an Administrator and run

```bash
wsl --install Ubuntu-24.04
wsl --set-default Ubuntu-24.04
```

## On Linux WSL System

Open an Ubuntu WSL terminal and follow the instructions.

### Step 1: [OPTIONAL] Setup proxy

Edit `/etc/bash.bashrc` and append lines with http_proxy and https_proxy:

```bash
export http_proxy=""
export https_proxy=""
```

Open a visudo:

```bash
sudo visudo
```

After the line:

```bash
Defaults        env_reset
```

Add this line:

```bash
Defaults        env_keep = "http_proxy https_proxy"
```

Apply changes by sourcing the file:

```bash
source /etc/profile
```

### Step 2: Provide access to `/dev/dri/renderD12*` directory

Check that the `/dev/dri/renderD12*` directory exists. The output from `ls` command should be similar to this:

```bash
ls -ltrah /dev/dri

total 0
drwxr-xr-x  3 root root        100 Mar 24 16:00 .
crw-rw----  1 root render 226, 128 Mar 24 16:00 renderD128
crw-rw----  1 root video  226,   0 Mar 24 16:00 card0
drwxr-xr-x  2 root root         80 Mar 24 16:00 by-path
drwxr-xr-x 16 root root       3.5K Mar 24 16:00 ..
```

If there is no `/dev/dri/renderD12*` directory please try running:

```bash
sudo modprobe vgem
```

and check once again.

### Step 3: Add user to the `render` group

To have permission to use GPU device, the user has to belong to the `render` group.
Please follow the instructions:

```bash
sudo gpasswd -a ${USER} render
newgrp render
```

Confirm that listed groups to which you belong contain the `render` group:

```bash
groups ${USER}
```

### Step 4: Install GPU libraries

Follow the instructions to add necessary repositories and install GPU libraries:

```bash
cd $HOME
wget -qO - https://repositories.intel.com/gpu/intel-graphics.key | sudo gpg --dearmor --output /usr/share/keyrings/intel-graphics.gpg
echo 'deb [arch=amd64,i386 signed-by=/usr/share/keyrings/intel-graphics.gpg] https://repositories.intel.com/gpu/ubuntu noble unified' | sudo tee /etc/apt/sources.list.d/intel.gpu.noble.list
sudo apt update
sudo apt-get install -y libze-dev intel-opencl-icd intel-media-va-driver-non-free libmfx1 libvpl2 libegl-mesa0 libegl1-mesa-dev libgbm1 libgl1-mesa-dev libgl1-mesa-dri libglapi-mesa libgles2-mesa-dev libglx-mesa0 libigdgmm12 libxatracker2 mesa-va-drivers mesa-vdpau-drivers mesa-vulkan-drivers va-driver-all
```

### Step 5: Add OpenVINO™ Toolkit and Deep Learning Streamer repositories

Follow the instructions to add necessary repositories for Deep Learning Streamer Framework and OpenVINO™ Toolkit:

```bash
cd $HOME
sudo -E wget -O- https://apt.repos.intel.com/intel-gpg-keys/GPG-PUB-KEY-INTEL-SW-PRODUCTS.PUB | gpg --dearmor | sudo tee /usr/share/keyrings/intel-gpg-archive-keyring.gpg > /dev/null
sudo -E wget -O- https://apt.repos.intel.com/edgeai/dlstreamer/GPG-PUB-KEY-INTEL-DLS.gpg | sudo tee /usr/share/keyrings/dls-archive-keyring.gpg > /dev/null
echo "deb [signed-by=/usr/share/keyrings/dls-archive-keyring.gpg] https://apt.repos.intel.com/edgeai/dlstreamer/$(source /etc/os-release && echo $VERSION_CODENAME) main" | sudo tee /etc/apt/sources.list.d/intel-dlstreamer.list
sudo bash -c 'echo "deb [signed-by=/usr/share/keyrings/intel-gpg-archive-keyring.gpg] https://apt.repos.intel.com/openvino/2025 ubuntu24 main" | sudo tee /etc/apt/sources.list.d/intel-openvino-2025.list'
```

### Step 6: Install Deep Learning Streamer Pipeline Framework

Follow the instructions to install Deep Learning Streamer and its dependencies:

```bash
sudo apt update
sudo apt install intel-dlstreamer
```

### Step 7: Download yolo11s model

If you would like to execute sample pipelines, please download yolo11s model as the sample one for these pipelines:

```bash
mkdir $HOME/models
export MODELS_PATH=$HOME/models
sudo apt install -y python3.12-venv
/opt/intel/dlstreamer/samples/download_public_models.sh yolo11s coco128
```

### Step 8: Execute sample pipelines

The Deep Learning Streamer Framework is ready to use. Now you can source the environment setup:

```bash
source /opt/intel/dlstreamer/scripts/setup_dls_env.sh
```

and execute a sample pipeline with inference on the CPU:

```bash
gst-launch-1.0 urisourcebin buffer-size=4096 uri=https://videos.pexels.com/video-files/1192116/1192116-sd_640_360_30fps.mp4 ! decodebin3 ! gvadetect model=$MODELS_PATH/public/yolo11s/INT8/yolo11s.xml device=CPU pre-process-backend=ie ! queue ! gvawatermark ! videoconvertscale ! gvafpscounter ! autovideosink sync=false
```

The inference can be done on a GPU device with a better overall performance:

```bash
gst-launch-1.0 urisourcebin buffer-size=4096 uri=https://videos.pexels.com/video-files/1192116/1192116-sd_640_360_30fps.mp4 ! decodebin3 ! gvadetect model=$MODELS_PATH/public/yolo11s/INT8/yolo11s.xml device=GPU pre-process-backend=opencv ! queue ! gvawatermark ! videoconvertscale ! gvafpscounter ! autovideosink sync=false
```

> **NOTE:** There is no current support for Video Acceleration API (VA-API) within WSL.


------------------------------------------------------------------------

> **\*** *Other names and brands may be claimed as the property of
> others.*
