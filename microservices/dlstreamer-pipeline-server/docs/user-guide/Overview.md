# Deep Learning Streamer Pipeline Server

Deep Learning Streamer Pipeline Server (DL Streamer Pipeline Server) is a Python-based, interoperable containerized microservice for easy development and deployment of video analytics pipelines.

## Overview

DL Streamer Pipeline Server microservice is built on top of [GStreamer](https://gstreamer.freedesktop.org/documentation/) and [Deep Learning Streamer (DL Streamer)](https://github.com/open-edge-platform/dlstreamer/blob/master/docs/source/index.md), providing video ingestion and deep learning inferencing functionalities.

Video analytics involves the conversion of video streams into valuable insights through the application of video processing, inference, and analytics operations. It finds applications in various business sectors including healthcare, retail, entertainment, and industrial domains. The algorithms utilized in video analytics are responsible for performing tasks such as object detection, classification, identification, counting, and tracking on the input video stream.

## How it Works

![DL Streamer Pipeline Server Architecture](./images/dls-pipelineserver-simplified-arch.png)

Here is the high level description of functionality of DL Streamer Pipeline Server module:

- **RESTful Interface**</br>
  Exposes RESTful endpoints to discover, start, stop and customize pipelines in JSON format.

- **DL Streamer Pipeline Server Core**</br>
  Manages and processes the REST requests interfacing with the core DL Streamer Pipeline Server components and Pipeline Server Library.

- **DL Streamer Pipeline Server Configuration handler**</br>
  Reads the contents of config file and accordingly constructs/starts pipelines. Dynamic configuration change is supported via REST API.

- **GST UDF Loader**</br>
  DL Streamer Pipeline Server provides a [GStreamer plugin](https://gstreamer.freedesktop.org/documentation/plugins_doc.html?gi-language=c) - `udfloader` using which users can configure and load arbitrary UDFs. With `udfloader`, DL Streamer Pipeline Server provides an easy way to bring user developed programs and run them as a part of GStreamer pipelines. A User Defined Function (UDF) is a chunk of user code that can transform video frames and/or manipulate metadata. For example, a UDF can act as filter, preprocessor, classifier or a detector. These User Defined Functions can be developed in Python.

- **DL Streamer Pipeline Server Publisher**</br>
  Supports publishing metadata to file, MQTT/Kafka message brokers and frame along with metadata to MQTT message broker. We also support publishing metadata and frame over OPCUA. The frames can also be saved on S3 compliant storage.

- **DL Streamer Pipeline Server Model Update**</br>
  Supports integration with Model Registry service [Model Registry](https://docs.openedgeplatform.intel.com/dev/edge-ai-libraries/model-registry/index.html) for model download, deployment and management.

- **Open Telemetry**</br>
  Supports gathering metrics over Open Telemetry for seamless visualization and analysis.
