# Deep Learning Streamer Pipeline Server

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/dlstreamer-pipeline-server">
     GitHub project
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/dlstreamer-pipeline-server/README.md">
     Readme
  </a>
</div>
hide_directive-->

Deep Learning Streamer Pipeline Server (DL Streamer Pipeline Server) is a Python-based,
interoperable containerized microservice for easy development and deployment of video analytics
pipelines.

## Overview

DL Streamer Pipeline Server microservice is built on top of [GStreamer](https://gstreamer.freedesktop.org/documentation/)
and [Deep Learning Streamer (DL Streamer)](https://github.com/open-edge-platform/dlstreamer/tree/main),
providing video ingestion and deep learning inferencing functionalities.

Video analytics involves the conversion of video streams into valuable insights through the
application of video processing, inference, and analytics operations. It finds applications
in various business sectors including healthcare, retail, entertainment, and industrial domains.
The algorithms utilized in video analytics are responsible for performing tasks such as object
detection, classification, identification, counting, and tracking on the input video stream.

## How it Works

![DL Streamer Pipeline Server architecture](./images/dls-pipelineserver-simplified-arch.png)

Here is the high level description of functionality of DL Streamer Pipeline Server module:

- **RESTful Interface**

  Exposes RESTful endpoints to discover, start, stop and customize pipelines in JSON format.

- **DL Streamer Pipeline Server Core**

  Manages and processes the REST requests interfacing with the core DL Streamer Pipeline Server
  components and Pipeline Server Library.

- **DL Streamer Pipeline Server Configuration handler**

  Reads the contents of a config file and accordingly constructs/starts pipelines. Dynamic
  configuration change is supported via REST API.

- **GST UDF Loader**

  DL Streamer Pipeline Server provides a [GStreamer plugin](https://gstreamer.freedesktop.org/documentation/plugins_doc.html?gi-language=c) - `udfloader`, which can be used to configure and load arbitrary UDFs. With
  `udfloader`, DL Streamer Pipeline Server provides an easy way to bring user developed programs
  and run them as a part of GStreamer pipelines. A User Defined Function (UDF) is a chunk of
  user code that can transform video frames and/or manipulate metadata. For example, a UDF can
  act as filter, preprocessor, classifier or a detector. These User Defined Functions can be
  developed in Python.

- **DL Streamer Pipeline Server Publisher**

  Supports publishing metadata to a file, MQTT/Kafka message brokers and frame along with
  metadata to a MQTT message broker. It also supports publishing metadata and frame over OPCUA.
  The frames can also be saved on S3 compliant storage.

- **DL Streamer Pipeline Server Model Update**

  Supports integration with the Model Registry service - [Model Registry](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/model-registry/index.html) for model download, deployment and management.

- **Open Telemetry**

  Supports gathering metrics over Open Telemetry for seamless visualization and analysis.

<!--hide_directive
:::{toctree}
:hidden:

overview-architecture
system-requirements
get-started
troubleshooting-guide
how-to-change-dlstreamer-pipeline
how-to-use-gpu-for-decode-and-inference
how-to-use-cpu-for-decode-and-inference
how-to-autostart-pipelines
how-to-launch-configurable-pipelines
how-to-perform-webrtc-frame-streaming
how-to-start-dlsps-mqtt-publish
how-to-store-s3-frame
how-to-store-metadata-influxdb
how-to-publish-metadata-over-ros2
how-to-launch-and-manage-pipeline
how-to-use-rtsp-camera-as-video-source
how-to-run-udf-pipelines
how-to-deploy-with-helm
how-to-use-image-file-as-source-over-request-payload
how-to-download-and-run-yolo-models
how-to-build-from-source
how-to-add-system-timestamps-to-metadata
api-reference
environment-variables
advanced-guide/Overview
release_notes/Overview

:::
hide_directive-->
