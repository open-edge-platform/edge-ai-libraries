<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Standalone `gvaopticalflow` (lab smoke)

Self-contained GStreamer plugin that mirrors the dlstreamer element without
requiring a full DL Streamer build. Vendors `GstGVATensorMeta` and links an
installed `optical_flow_sdk` (OpenCL).

Upstream home remains dlstreamer `feat/gvaopticalflow` (PR deferred).

## Lab (Series 2 — `labrat@10.91.82.130`)

```bash
# micromamba env with gstreamer + headers (one-time)
micromamba create -y -n gst-dev -c conda-forge gstreamer gst-plugins-base pkg-config cmake cxx-compiler
micromamba activate gst-dev

cmake -S . -B build -DCMAKE_BUILD_TYPE=Release \
  -Doptical_flow_sdk_DIR=$HOME/optical-flow-sdk/install/lib/cmake/optical_flow_sdk \
  -DOpenCL_INCLUDE_DIR=$HOME/opencv/3rdparty/include/opencl/1.2 \
  -DOpenCL_LIBRARY=/usr/lib/x86_64-linux-gnu/libOpenCL.so.1
cmake --build build -j

export GST_PLUGIN_PATH=$PWD/build
export LD_LIBRARY_PATH=$CONDA_PREFIX/lib:$LD_LIBRARY_PATH
gst-inspect-1.0 gvaopticalflow
gst-launch-1.0 videotestsrc num-buffers=30 pattern=ball ! \
  video/x-raw,format=NV12,width=640,height=480,framerate=30/1 ! \
  gvaopticalflow preset=fast device=GPU ! fakesink sync=false
```

**Lab smoke 2026-11-10:** `gst-inspect` OK; `gst-launch` 30×640×480 NV12 GPU
DIS Fast → EOS (ControlMaster `arc`). Device path uses strided Y upload +
ping-pong (`docs/device_import.md`).

**Consumer example:**

```bash
python3 examples/flow_consumer.py
# frames=12 buffers_with_gva_tensor_meta=11  (frame0 has no prev)
```
