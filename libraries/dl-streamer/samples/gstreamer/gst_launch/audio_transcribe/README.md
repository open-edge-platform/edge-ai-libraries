# GVA Audio Transcribe Element

## Table of Contents

1. [Overview](#overview)
   - [Model Type Support](#model-type-support)
2. [Quick Usage](#quick-usage)
3. [Installation](#installation)
   - [Install DLstreamer](#install-dlstreamer)
   - [OpenVINO GenAI Dependencies](#openvino-genai-dependencies)
   - [Build DL Streamer](#build-dl-streamer)
4. [Setup and Configuration](#setup-and-configuration)
   - [Create Workspace](#create-workspace)
   - [Get Whisper Model Files](#get-whisper-model-files)
   - [GPU Prerequisites](#to-use-gpu-device-for-inference)
5. [Running on Host](#running-on-host)
   - [Script Permissions](#permission-of-the-script)
   - [WAV File Transcription](#launch-on-a-test-wav-file)
   - [Live Microphone Transcription](#launch-using-the-microphone)
   - [Video Audio Transcription](#launch-using-video-demux)
6. [Running Using Docker](#run-using-docker)
   - [Clone Repository](#clone-the-repo)
   - [Docker Build](#docker-build)
   - [Model Setup for Docker](#set-up-to-download-models)
   - [Download Models](#download-model)
   - [Docker Run](#docker-run)
7. [Configuration](#configuration)
   - [Properties](#properties)
8. [Troubleshooting](#troubleshooting)
---


GStreamer element for audio transcription using speech recognition models.

## Overview

This element provides audio transcription capabilities with an extensible handler interface. Currently supports:

- **Whisper models** (primary support) - OpenVINO GenAI backend

### Model Type Support

- `whisper` - Fully supported (OpenVINO GenAI)


## Quick Usage

```bash
# Basic Whisper transcription
GST_DEBUG=gvaaudiotranscribe:4 gst-launch-1.0 filesrc location=</path/to/file.wav> ! decodebin3 ! audioresample ! audioconvert ! audio/x-raw,channels=1,format=S16LE,rate=16000 ! audiomixer output-buffer-duration=100000000 ! gvaaudiotranscribe model=whisper-base device=CPU ! fakesink
```

# RUN ON HOST

# Install DLstreamer

Please follow DLstreamer official docs for installation steps: https://dlstreamer.github.io/dev_guide/advanced_install/advanced_install_guide_compilation.html 

Note: Follow through step 8 of the documentation, then install OpenVINO GenAI as mentioned below. 

# OpenVINO GenAI dependencies
```bash
cd ~
wget 'https://storage.openvinotoolkit.org/repositories/openvino_genai/packages/2025.3/linux/openvino_genai_ubuntu24_2025.3.0.0_x86_64.tar.gz'
tar xzf openvino_genai_ubuntu24_2025.3.0.0.dev20250809_x86_64.tar.gz
```

Need to do this every time you reactivate the environment:
```bash
source openvino_genai_ubuntu24_2025.3.0.0.dev20250809_x86_64/setupvars.sh
```

# Build DL Streamer 
Note: This step is adapted from the official documentation, tweaking a couple of parameters for the audio transcription element. 

```bash
cd ~/edge-ai-libraries/libraries/dl-streamer

mkdir build
cd build

export PKG_CONFIG_PATH="/opt/intel/dlstreamer/gstreamer/lib/pkgconfig:${PKG_CONFIG_PATH}"
source /opt/intel/openvino_2025/setupvars.sh

cmake -DENABLE_PAHO_INSTALLATION=OFF -DENABLE_RDKAFKA_INSTALLATION=OFF -DENABLE_VAAPI=ON -DENABLE_SAMPLES=ON -DENABLE_GENAI=on ..
make -j "$(nproc)"
```

Set up the environment using the following step: [Environment Setup](https://dlstreamer.github.io/dev_guide/advanced_install/advanced_install_guide_compilation.html#step-10-set-up-environment)


# Prepare to run the pipelines

## Create workspace
```bash
mkdir ~/whisper-poc
cd ~/whisper-poc
```

## Get Whisper model files

These steps are adapted from the original whisper_speech_recognition sample in OpenVINO GenAI: https://github.com/openvinotoolkit/openvino.genai/blob/releases/2025/3/samples/cpp/whisper_speech_recognition/README.md

```bash
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/releases/2025/3/samples/requirements.txt
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/releases/2025/3/samples/deployment-requirements.txt
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/releases/2025/3/samples/export-requirements.txt

```

You might want to create a Python virtual environment and activate it if you don't want to install packages for your user. This is not strictly required though.

Install those requirements:
```bash
python3 -m venv ~/whisper-env
source ~/whisper-env/bin/activate
pip install --upgrade-strategy eager -r ../../requirements.txt
```

Download & convert the Whisper model:
```bash
optimum-cli export openvino --trust-remote-code --model openai/whisper-base whisper-base
```
### To use GPU device for inference 

There are few prerequisites that is required follow the Documentation for more details 
- [GPU driver installation](../../../../docs/source/get_started/install/install_guide_ubuntu.md#step-1-install-prerequisites), after running [DLS_install_prerequisites.sh](../../../../scripts/DLS_install_prerequisites.sh) script and reboot your machine 
```bash
    #verify if the GPU device is popping up
     clinfo | grep 'Device'
```
- [GPU Device selection](../../../../docs/source/dev_guide/gpu_device_selection.md)


## Finally, actually run the full pipeline using sample:

### Permission of the script
```bash
cd ~/edge-ai-libraries/libraries/dl-streamer/samples/gstreamer/gst_launch/audio_transcribe
chmod a+x /audio_transcribe.sh
``` 

### Launch on a test WAV file:

```bash
 ./audio_transcribe.sh --input-source=${HOME}/<filename.wav> --models-path=${HOME}/path/to/model-directory/ --device=CPU --mode=video
```

### Launch using the microphone:
```bash
./audio_transcribe.sh --models-path=${HOME}/path/to/model-directory/ --device=CPU --mode=live

```

### Launch using video demux:
```bash
./audio_transcribe.sh --input-source=${HOME}/<filename.mp4> --models-path=${HOME}/path/to/model-directory/ --device=CPU --mode=video
```

# RUN USING DOCKER 


### Clone the repo
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git && cd edge-ai-librarie
git submodule update --init libraries/dl-streamer/thirdparty/spdlog
```

### Docker build 

```bash
docker build -f docker/ubuntu/ubuntu24.Dockerfile  -t dlstreamer-ubuntu24-dev-asr .
```

### Set up to download models
```bash
cd ~/
python3 -m venv ~/python3-env
source ~/python3-env/bin/activate
# Install dependencies to download and convert Whisper model

wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/releases/2025/3/samples/requirements.txt
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/releases/2025/3/samples/deployment-requirements.txt
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/releases/2025/3/samples/export-requirements.txt

pip install --upgrade-strategy eager -r ./requirements.txt
```

### Download model

```bash
mkdir -p ~/data
cd ~/data
optimum-cli export openvino --trust-remote-code --model openai/whisper-base whisper-base
# Sample wave file 
wget https://storage.openvinotoolkit.org/models_contrib/speech/2021.2/librispeech_s5/how_are_you_doing_today.wav
```


### Docker run 
```bash
# Run interactively 
docker run -it -v ~/data:/data dlstreamer-ubuntu24-dev-asr:latest bash 
# Run the command inside docker
GST_DEBUG=gvaaudiotranscribe:4 gst-launch-1.0 filesrc location=/data/how_are_you_doing_today.wav ! decodebin3 ! audioresample ! audioconvert ! audio/x-raw,channels=1,format=S16LE,rate=16000 ! audiomixer output-buffer-duration=100000000 ! gvaaudiotranscribe model=/data/whisper-base device=CPU ! fakesink
# Or 
# Quick try
docker run -it -v ~/data:/data dlstreamer-ubuntu24-test:latest bash -c "GST_DEBUG=gvaaudiotranscribe:4 gst-launch-1.0 filesrc location=/data/how_are_you_doing_today.wav ! decodebin3 ! audioresample ! audioconvert ! audio/x-raw,channels=1,format=S16LE,rate=16000 ! audiomixer output-buffer-duration=100000000 ! gvaaudiotranscribe model=/data/whisper-base device=CPU ! fakesink"
```

### Properties

- `model` - Path to model (directory for Whisper, custom path for other models)
- `model_type` - Model type: `whisper` (supported), or your custom type
- `device` - Inference device: `CPU`, `GPU`
- `language` - Language code (e.g., `<|en|>` for English), currently supoports english
- `task` - Task type: `transcribe` or `translate`, currently supports transcription 


### Troubleshooting 

```bash 
Failed to load plugin '/home/intel/edge-ai-libraries/libraries/dl-streamer/build/intel64/Release/lib/libgstvideoanalytics.so': 
/home/intel/edge-ai-libraries/libraries/dl-streamer/build/intel64/Release/lib/libgstvideoanalytics.so: undefined symbol: _ZTVN2ov5genai11PerfMetricsE
```
- If you get this error, it's mostly because the OpenVINO and OpenVINO GenAI versions do not match. Make sure you have the same version of openvino_toolkit and openvino_genAI [in this case 2025.3.0]

```bash 
gst-inspect: command not found
or 
no element named gvaaudiotranscribe
```
- Recheck and set your environment using [Environment Setup](https://dlstreamer.github.io/dev_guide/advanced_install/advanced_install_guide_compilation.html#step-10-set-up-environment), [Environment SetupScript](../../../../scripts/setup_env.sh)

- If you try to use an unsupported model type:

```bash
# This will show a helpful error message
gst-launch-1.0 audiotestsrc ! audioconvert ! audioresample ! \
    "audio/x-raw,format=S16LE,rate=16000,channels=1" ! \
    gvaaudiotranscribe model=/path/to/model model_type=custom_model ! \
    fakesink
```

**Error output:**
```bash
Model type 'custom_model' is not currently supported. 
Currently supported: 'whisper'. 
Feel free to implement support for 'custom_model' by extending the GvaAudioTranscribeHandler interface! 
See gstgvaaudiotranscribehandler.h for the extensible interface.
```






