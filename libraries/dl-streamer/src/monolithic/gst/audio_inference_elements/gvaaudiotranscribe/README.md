# GVA Audio Transcribe Element

GStreamer element for audio transcription using speech recognition models.

## Overview

This element provides audio transcription capabilities with an extensible handler interface. Currently supports:

- **Whisper models** (primary support) - OpenVINO GenAI backend
- **Extensible handler interface** - Users can implement custom model handlers

### Key Features

- Real-time audio transcription
- Configurable language and task settings
- Optional timestamp generation
- Device selection (CPU, GPU)
- Extensible architecture for custom models
- GStreamer metadata integration

### Model Type Support

- `whisper` - Fully supported (OpenVINO GenAI)
- Custom types -  Implement your own! See [CUSTOM_HANDLERS.md](CUSTOM_HANDLERS.md)

## Quick Usage

```bash
# Basic Whisper transcription
GST_DEBUG=gvaaudiotranscribe:4 gst-launch-1.0 filesrc location=</path/to/file.wav> ! decodebin3 ! audioresample ! audioconvert ! audio/x-raw,channels=1,format=S16LE,rate=16000 ! audiomixer output-buffer-duration=100000000 ! gvaaudiotranscribe model=whisper-base device=CPU ! fakesink
```

# RUN ON HOST

# Install dependencies
This adapted from the official docs: https://dlstreamer.github.io/dev_guide/advanced_install/advanced_install_guide_compilation.html
```
sudo apt-get update && \
sudo apt-get install -y wget vainfo xz-utils python3-pip python3-gi gcc-multilib libglib2.0-dev \
    flex bison autoconf automake libtool libogg-dev make g++ libva-dev yasm libglx-dev libdrm-dev \
    python-gi-dev python3-dev unzip libgflags-dev libcurl4-openssl-dev \
    libgirepository1.0-dev libx265-dev libx264-dev libde265-dev gudev-1.0 libusb-1.0 nasm python3-venv \
    libcairo2-dev libxt-dev libgirepository1.0-dev libgles2-mesa-dev wayland-protocols \
    libssh2-1-dev cmake git valgrind numactl libvpx-dev libopus-dev libsrtp2-dev libxv-dev \
    linux-libc-dev libpmix2t64 libhwloc15 libhwloc-plugins libxcb1-dev libx11-xcb-dev \
    ffmpeg librdkafka-dev libpaho-mqtt-dev libopencv-dev libpostproc-dev libavfilter-dev libavdevice-dev \
    libswscale-dev libswresample-dev libavutil-dev libavformat-dev libavcodec-dev libtbb12 libxml2-dev
```

```
sudo apt-get install --reinstall ffmpeg libpostproc-dev libavfilter-dev libavdevice-dev \
            libswscale-dev libswresample-dev libavutil-dev libavformat-dev libavcodec-dev
```

```
sudo apt-get install --reinstall libopencv-dev
```

# Build newer version of gstreamer.

Note: apt package for gstreamer on ubuntu 24.04 by default installs version 1.24.1 but there are some plugins that are not implicitly installed therefore recommendation is to follow the above mention documentation and build gstreamer from source 

```bash 
python3 -m venv ~/python3venv
source ~/python3venv/bin/activate

pip install --upgrade pip==24.0
pip install meson==1.4.1 ninja==1.11.1.1

cd ~
git clone https://gitlab.freedesktop.org/gstreamer/gstreamer.git

cd ~/gstreamer
git switch -c "1.26.4" "tags/1.26.4"
export PKG_CONFIG_PATH=/usr/lib/x86_64-linux-gnu/pkgconfig/:/usr/local/lib/pkgconfig:$PKG_CONFIG_PATH
sudo ldconfig
meson setup -Dexamples=disabled -Dtests=disabled -Dvaapi=enabled -Dgst-examples=disabled --buildtype=release --prefix=/opt/intel/dlstreamer/gstreamer --libdir=lib/ --libexecdir=bin/ build/
ninja -C build
sudo env PATH=~/python3venv/bin:$PATH meson install -C build/
```

**EXIT THE CURRENT SESSION AND REOPEN IT**
The python environment doesn't need to be active anymore, and it's already contaminated your current session with variables


# Clone dl-streamer repo & check out the appropriate branch
```
cd ~
git clone https://github.com/dlstreamer.git
git checkout audio_transcription
git submodule update --init
```

# OpenVINO & OpenVINO GenAI dependencies
```
cd ~
wget 'https://storage.openvinotoolkit.org/repositories/openvino/packages/nightly/2025.3.0-19730-c619ac6a596/openvino_toolkit_ubuntu24_2025.3.0.dev20250809_x86_64.tgz'
wget 'https://storage.openvinotoolkit.org/repositories/openvino_genai/packages/nightly/2025.3.0.0.dev20250809/openvino_genai_ubuntu24_2025.3.0.0.dev20250809_x86_64.tar.gz'
tar xzf openvino_genai_ubuntu24_2025.3.0.0.dev20250809_x86_64.tar.gz
tar xzf openvino_toolkit_ubuntu24_2025.3.0.dev20250809_x86_64.tgz
```

Need to do this every time you reactivate the environment:
```
source openvino_genai_ubuntu24_2025.3.0.0.dev20250809_x86_64/setupvars.sh
source openvino_toolkit_ubuntu24_2025.3.0.dev20250809_x86_64/setupvars.sh
```

# Set many environment variables needed to find the tools configured earlier. These are from the official advanced DLStreamer compiling guide.
```
export GST_PLUGIN_PATH="$HOME/dlstreamer/build/intel64/Release/lib:/opt/intel/dlstreamer/gstreamer/lib/gstreamer-
1.0:/usr/lib/x86_64-linux-gnu/gstreamer-1.0"
export LD_LIBRARY_PATH="/opt/intel/dlstreamer/gstreamer/lib:$HOME/dlstreamer/build/intel64/Release/lib:/usr/lib:/usr/local/lib:$LD_LIBRARY_PATH"
export LIBVA_DRIVERS_PATH="/usr/lib/x86_64-linux-gnu/dri"
export GST_VA_ALL_DRIVERS="1"
export PATH="/opt/intel/dlstreamer/gstreamer/bin:$HOME/dlstreamer/build/intel64/Release/bin:$HOME/.local/bin:$HOME/python3venv/bin:$PATH"
export PKG_CONFIG_PATH="/usr/local/lib/pkgconfig:$HOME/dlstreamer/build/intel64/Release/lib/pkgconfig:/usr/lib/x86_64-linux-gnu/pkgconfig:/opt/intel/dlstreamer/gstreamer/lib/pkgconfig:$PKG_CONFIG_PATH"
export GST_PLUGIN_FEATURE_RANK=${GST_PLUGIN_FEATURE_RANK},ximagesink:MAX
```

# Set this include path too. Need to fix this so it's not needed, this is needed because of a cmake configuration bug in this PoC code:
```
export CPLUS_INCLUDE_PATH=$OpenVINOGenAI_DIR/../../runtime/include
```


# Build DL Streamer
```
cd ~/dlstreamer
mkdir build
cd build
cmake -DENABLE_PAHO_INSTALLATION=ON -DENABLE_RDKAFKA_INSTALLATION=ON -DENABLE_VAAPI=ON -DENABLE_SAMPLES=ON -DENABLE_GENAI=on ..
make -j $(nproc)
```

# Prepare to run the pipelines

## Create workspace
```
mkdir ~/whisper-poc
cd ~/whisper-poc
```

## Get whisper model files

These steps adapted from the original whisper_speech_recognition sample in OpenVINO GenAI: https://github.com/openvinotoolkit/openvino.genai/blob/master/samples/cpp/whisper_speech_recognition/README.md

```
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/master/samples/requirements.txt
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/master/samples/deployment-requirements.txt
wget https://raw.githubusercontent.com/openvinotoolkit/openvino.genai/refs/heads/master/samples/export-requirements.txt
```

You might want to create a python virtual environment and activate it if you don't want to install stuff for your user. Not strictly needed though.

Install those requirements:
```
python3 -m venv ~/whisper-env
source ~/whisper-env/bin/activate
pip install --upgrade-strategy eager -r ../../requirements.txt
```

Download & convert the whisper model:
```
optimum-cli export openvino --trust-remote-code --model openai/whisper-base whisper-base
```

## Finally actually run the full pipeline:

### Troubleshooting
 gst-launch to find the transcription feature, it was saying no element "gstgvaaudiotranscribe". If you get this same error, try running this first. Must have cached it initially? Not sure:
```
gst-inspect-1.0 ~/dlstreamer/build/intel64/Release/lib/libgstvideoanalytics.so
```

### Launch on a test wav file:

```
GST_DEBUG=gvaaudiotranscribe:4 gst-launch-1.0 filesrc location=<path/to/wavfile> ! decodebin3 ! audioresample ! audioconvert ! audio/x-raw,channels=1,format=S16LE,rate=16000 ! audiomixer output-buffer-duration=100000000 ! gvaaudiotranscribe model=whisper-base device=CPU model_type=whisper ! fakesink
```

### Launch using the microphone
```
GST_DEBUG=gvaaudiotranscribe:4 gst-launch-1.0     pulsesrc buffer-time=2000000 ! audioconvert ! audioresample ! audio/x-raw,format=S16LE,channels=1,rate=16000 ! queue max-size-buffers=100 max-size-time=0 max-size-bytes=0 ! gvaaudiotranscribe model=whisper-base device=CPU model_type=whisper ! fakesink
```

### Launch using video demux
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
git clone https://github.com/dlstreamer.git && cd dlstreamer
git checkout audio-transcription
git submodule update --init --recursive
```

### Docker build

```bash
docker build -f docker/dlstreamer_dev_ubuntu24_asr.Dockerfile -t dlstreamer-ubuntu24-dev-asr .
```

### Setup to download models
```bash
cd ~/
python3 -m venv ~/python3-env
source ~/python3-env/bin/activate
# install dependencies to download and convert whisper-model

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
#sample wave file 
wget https://storage.openvinotoolkit.org/models_contrib/speech/2021.2/librispeech_s5/how_are_you_doing_today.wav
```

## Extensible Handler Interface

This element features an extensible handler interface that allows users to implement support for custom speech recognition models.

### Currently Supported Models

- **Whisper** (`model_type=whisper`) - \u2705 Fully supported via OpenVINO GenAI

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


### Docker run 
```bash
# run iteractively 
docker run -it -v ~/data:/data dlstreamer-ubuntu24-dev-asr:latest bash 
#run the command inside docker
GST_DEBUG=gvaaudiotranscribe:4 gst-launch-1.0 filesrc location=/data/how_are_you_doing_today.wav ! decodebin3 ! audioresample ! audioconvert ! audio/x-raw,channels=1,format=S16LE,rate=16000 ! audiomixer output-buffer-duration=100000000 ! gvaaudiotranscribe model=/data/whisper-base device=CPU ! fakesink
or 
#quick try
docker run -it -v ~/data:/data dlstreamer-ubuntu24-test:latest bash -c "GST_DEBUG=gvaaudiotranscribe:4 gst-launch-1.0 filesrc location=/data/how_are_you_doing_today.wav ! decodebin3 ! audioresample ! audioconvert ! audio/x-raw,channels=1,format=S16LE,rate=16000 ! audiomixer output-buffer-duration=100000000 ! gvaaudiotranscribe model=/data/whisper-base device=CPU ! fakesink"
```

