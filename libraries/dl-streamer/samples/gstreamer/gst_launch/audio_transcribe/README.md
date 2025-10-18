# GVA Audio Transcribe Element

## Table of Contents

1. [Overview](#overview)
   - [Model Type Support](#model-type-support)
2. [Quick Usage](#quick-usage)
3. [Installation](#installation)
   - [Install DLstreamer](#install-dlstreamer)
4. [Model Preparation](#model-preparation)
   - [Create Workspace](#create-workspace)
   - [Get Whisper Model Files](#get-whisper-model-files)
   - [GPU Prerequisites](#to-use-gpu-device-for-inference)
5. [Demo Script Execution](#demo-script-execution)
   - [Script Permissions](#permission-of-the-script)
   - [WAV File Transcription](#launch-on-a-test-wav-file)
   - [Live Microphone Transcription](#launch-using-the-microphone)
   - [Video Audio Transcription](#launch-using-video-demux)
6. [Audio Transcription Pipeline Using GVA Elements](#audio-transcription-pipeline-using-gvametaconvert-and-gvametapublish)
7. [Configuration](#configuration)
   - [Properties](#properties)
8. [Troubleshooting](#troubleshooting)
---

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

# Install DLstreamer

Please follow DLstreamer official docs for installation steps: https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/dl-streamer/dev_guide/advanced_install/advanced_install_guide_compilation.html 

Note: This element required OpenVINO GenAI as mentioned below. 

# Model Preparation

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


## Demo Script Execution:

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

### Audio Transcription Pipeline Using `gvametaconvert` and `gvametapublish`

```bash
GST_DEBUG=gvaaudiotranscribe:4 gst-launch-1.0  filesrc location=${HOME}/<filename>.mp4 ! qtdemux name=demux demux.audio_0 ! decodebin ! audioconvert ! audioresample ! audio/x-raw,channels=1,format=S16LE,rate=16000 ! audiomixer output-buffer-duration=100000000 ! gvaaudiotranscribe model=${HOME}/path/to/whisper-model-dir device=CPU model_type=whisper  ! gvametaconvert format=json ! gvametapublish method=file file-path=transcriptions.json ! fakesink
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






