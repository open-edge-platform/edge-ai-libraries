<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

<!--hide_directive
```{eval-rst}
.. meta::
   :description: Export a Visual Pipeline and Platform Evaluation Tool (ViPPET) pipeline variant as a standalone application that runs with Docker Compose.
   :keywords: ViPPET, export as app, pipeline variant, DL Streamer Pipeline Server, Docker Compose, MediaMTX.
```
hide_directive-->

# Exporting a Pipeline as an Application

Visual Pipeline and Platform Evaluation Tool (ViPPET) can export a pipeline variant as a
standalone application: a zip archive that runs the variant on Deep Learning Streamer
Pipeline Server (DL Streamer Pipeline Server) 2.0 with Docker Compose, without ViPPET. The
archive contains the model and input video the variant uses, so you can copy it to another
host and run it there.

> [!NOTE]
> In this release, only **Defect Detection** pipelines can be exported, that is, pipelines
> whose inference uses the *Pallet Defect Detection* model. *Export as app* is not shown for other
> pipelines. If a Defect Detection variant uses something the application does not support, an error
> message shows the reason.

## Export a Variant

1. Open the pipeline in the Pipeline Builder and select the variant, for example *CPU*,
   *GPU*, or *NPU*.
2. Save your changes. The application is built from the saved variant, so *Export as app* is
   disabled while the variant has unsaved changes.
3. Open the actions menu (the **⋮** button next to *Run pipeline*) and select *Export as app*.

The browser downloads `<pipeline>-<variant>-app.zip`, for example `defect-detection-cpu-app.zip`.

A variant can be exported when it reads one video file (`filesrc`) and uses only standard
DL Streamer elements. Variants with cameras, VLM elements (`gvagenai`),
Python modules (`gvapython`), additional file outputs, or inference on a GPU
other than the first one (`GPU.1`) or on a composite device (`AUTO`, `HETERO`, `MULTI`) are
not supported yet.

## Run the Application

The target host needs Linux with Docker, Docker Compose v2, `jq`, and `curl`, plus an Intel
GPU for GPU and NPU variants and an Intel NPU for NPU variants. The first start pulls the
DL Streamer Pipeline Server and MediaMTX images.

```bash
unzip defect-detection-cpu-app.zip
cd defect-detection-cpu-app
./start_app.sh               # start the stack
ID=$(./run.sh rtsp)          # start a pipeline instance, print its id
./status.sh "$ID"            # state and FPS of the instance
./stop_app.sh                # stop all instances and remove the containers
```

`./run.sh` takes the output as its first argument:

| Output     | Input Video         | Writes                                           |
| ---------- | ------------------- | ------------------------------------------------ |
| `fakesink` | loops until stopped | detection events only                            |
| `file`     | played once         | annotated video to `output/<name>.mp4`           |
| `rtsp`     | loops until stopped | annotated stream at `rtsp://<host>:18554/<name>` |

Every instance also writes its detection events to `output/<name>.jsonl`, one JSON object per
video frame. The app runs no MQTT broker, so a variant that publishes metadata over MQTT writes
it to this file instead.

The REST API of the pipeline server listens on `127.0.0.1:18080` and the RTSP server on port
`18554`, so the application can run next to ViPPET on the same host. The `README.md` in the
archive describes the outputs, the events format, and how to change the ports.

## Archive Content

| Path                                                            | Content                                                |
| --------------------------------------------------------------- | ------------------------------------------------------ |
| `compose.yml`                                                   | DL Streamer Pipeline Server 2.0 and MediaMTX           |
| `start_app.sh`, `run.sh`, `status.sh`, `stop.sh`, `stop_app.sh` | Scripts that drive the stack and its REST API          |
| `pipelines.json`                                                | The launch string of each output                       |
| `manifest.json`                                                 | Source pipeline and variant, ViPPET version, checksums |
| `assets/`                                                       | Model and input video files                            |
| `output/`                                                       | Videos and events written by the app                   |

The bundled model and video are third-party content with their own licenses. Check them before
you redistribute an exported application.
