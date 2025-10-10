# GVA Audio Transcribe Element

GStreamer element for audio transcription using speech recognition models.

## Overview

This element provides audio transcription capabilities with an extensible handler interface. Currently supports:

- **Whisper models** (primary support) - OpenVINO GenAI backend
- **Extensible handler interface** - Users can implement custom model handlers

### Model Type Support

- `whisper` - Fully supported (OpenVINO GenAI)
- Custom types - Implement your own! See [CUSTOM_HANDLERS.md](CUSTOM_HANDLERS.md)

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
```
cd ~
wget 'https://storage.openvinotoolkit.org/repositories/openvino_genai/packages/2025.3/linux/openvino_genai_ubuntu24_2025.3.0.0_x86_64.tar.gz.sha256'
tar xzf openvino_genai_ubuntu24_2025.3.0.0.dev20250809_x86_64.tar.gz
```

Need to do this every time you reactivate the environment:
```
source openvino_genai_ubuntu24_2025.3.0.0.dev20250809_x86_64/setupvars.sh
```

# Build DL Streamer 
Note: This step is adapted from the official documentation, tweaking a couple of parameters for the audio transcription element. 

```
cd ~/edge-ai-libraries/libraries/dl-streamer

mkdir build
cd build

export PKG_CONFIG_PATH="/opt/intel/dlstreamer/gstreamer/lib/pkgconfig:${PKG_CONFIG_PATH}"
source /opt/intel/openvino_2025/setupvars.sh

cmake -DENABLE_PAHO_INSTALLATION=OFF -DENABLE_RDKAFKA_INSTALLATION=OFF -DENABLE_VAAPI=ON -DENABLE_SAMPLES=ON -DENABLE_GENAI=on..
make -j "$(nproc)"
```

Set up the environment using the following step: [Environment Setup](https://dlstreamer.github.io/dev_guide/advanced_install/advanced_install_guide_compilation.html#step-10-set-up-environment)


# Prepare to run the pipelines

## Create workspace
```
mkdir ~/whisper-poc
cd ~/whisper-poc
```

## Get Whisper model files

These steps are adapted from the original whisper_speech_recognition sample in OpenVINO GenAI: https://github.com/openvinotoolkit/openvino.genai/blob/master/samples/cpp/whisper_speech_recognition/README.md

```
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/master/samples/requirements.txt
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/master/samples/deployment-requirements.txt
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/master/samples/export-requirements.txt
```

You might want to create a Python virtual environment and activate it if you don't want to install packages for your user. This is not strictly required though.

Install those requirements:
```
python3 -m venv ~/whisper-env
source ~/whisper-env/bin/activate
pip install --upgrade-strategy eager -r ../../requirements.txt
```

Download & convert the Whisper model:
```
optimum-cli export openvino --trust-remote-code --model openai/whisper-base whisper-base
```
### [Optional] To use GPU device for inference 

There are few prerequisites that is required follow the Documentation for more details [GPU Device selection](../../../../../docs/source/dev_guide/gpu_device_selection.md)


## Finally, actually run the full pipeline:


### Launch on a test WAV file:

```
GST_DEBUG=gvaaudiotranscribe:4 gst-launch-1.0 filesrc location=<path/to/wavfile> ! decodebin3 ! audioresample ! audioconvert ! audio/x-raw,channels=1,format=S16LE,rate=16000 ! audiomixer output-buffer-duration=100000000 ! gvaaudiotranscribe model=whisper-base device=CPU model_type=whisper ! fakesink
```

### Launch using the microphone:
```
GST_DEBUG=gvaaudiotranscribe:4 gst-launch-1.0     pulsesrc buffer-time=2000000 ! audioconvert ! audioresample ! audio/x-raw,format=S16LE,channels=1,rate=16000 ! queue max-size-buffers=100 max-size-time=0 max-size-bytes=0 ! gvaaudiotranscribe model=whisper-base device=CPU model_type=whisper ! fakesink
```

### Launch using video demux:
```bash
GST_DEBUG=gvaaudiotranscribe:4 \
gst-launch-1.0 filesrc location=<path/to/file.mp4/> ! \
    qtdemux name=demux \
    demux.audio_0 ! decodebin ! audioconvert ! audioresample ! \
    audio/x-raw,channels=1,format=S16LE,rate=16000 ! \
    audiomixer output-buffer-duration=100000000 ! \
    gvaaudiotranscribe model=whisper-base device=CPU model_type=whisper ! fakesink
```

# RUN USING DOCKER 


### Clone the repo
```bash
git clone https://github.com/open-edge-platform/edge-ai-libraries.git && cd edge-ai-librarie
git checkout whisper-audio-transcription
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

wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/master/samples/requirements.txt
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/master/samples/deployment-requirements.txt
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/master/samples/export-requirements.txt

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


## Extensible Handler Interface

This element features an extensible handler interface that allows users to implement support for custom speech recognition models.

### Currently Supported Models

- **Whisper** (`model_type=whisper`) - ✅ Fully supported via OpenVINO GenAI

### Adding Custom Model Support

Want to add support for your own speech recognition model? It's easy!

1. **See the detailed guide**: [CUSTOM_HANDLERS.md](CUSTOM_HANDLERS.md)
2. **Check examples**: Look at `examples/` directory for template implementations
3. **Implement the interface**: Inherit from `GvaAudioTranscribeHandler`
4. **Register your handler**: Add it to the model type selection logic
5. **Use it**: Set `model_type=your_custom_type`

### Example: Using Unsupported Model Type

If you try to use an unsupported model type:

```bash
# This will show a helpful error message
gst-launch-1.0 audiotestsrc ! audioconvert ! audioresample ! \
    "audio/x-raw,format=S16LE,rate=16000,channels=1" ! \
    gvaaudiotranscribe model=/path/to/model model_type=custom_model ! \
    fakesink
```

**Error output:**
```
Model type 'custom_model' is not currently supported. 
Currently supported: 'whisper'. 
Feel free to implement support for 'custom_model' by extending the GvaAudioTranscribeHandler interface! 
See gstgvaaudiotranscribehandler.h for the extensible interface.
```

### Properties

- `model` - Path to model (directory for Whisper, custom path for other models)
- `model_type` - Model type: `whisper` (supported), or your custom type
- `device` - Inference device: `CPU`, `GPU`
- `language` - Language code (e.g., `<|en|>` for English)
- `task` - Task type: `transcribe` or `translate`
- `return-timestamps` - Whether to include timestamps in output

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
- Recheck and set your environment using [Environment Setup](https://dlstreamer.github.io/dev_guide/advanced_install/advanced_install_guide_compilation.html#step-10-set-up-environment), [Environment SetupScript](../../../../../scripts/setup_env.sh)





