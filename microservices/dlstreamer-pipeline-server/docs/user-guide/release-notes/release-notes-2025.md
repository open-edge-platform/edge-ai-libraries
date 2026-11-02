# Release Notes: DL Streamer Pipeline Server 2025

## Version: 2025.2.0

**Release Date:** December 2025

**Added:**

- `souphttpsrc` element in docker file.

**Fixed:**

- Wrong formatting in compose file.
- Added missing `eis_mqtt_publish_doc.md` documentation.
- Fixed WebRTC GPU pipeline functionality for Xeon+dGPU hardware combinations.
- Updated Helm chart version in documentation and dockerhub to be in sync with current one.
- Resolved issue where videoconvert was dropping tensor data provided by gvametaconvert.
- Updated [Helm chart](https://hub.docker.com/layers/intel/dlstreamer-pipeline-server/2025.2.0/images/sha256-c878cc4d3606ebe242611b8ba7ffd551726c95a806e6bc415965d3f0f15a5a8f) on Dockerhub.
- Incorrect communication between containers has been fixed by configuring proper env variables.
- RSTP connection error recovery mechanism.

**Updated:**

- DL Streamer updated to 2025.2.0.

## v3.1.0

**Release Date:** August 2025

**Added:**

- Support for Ubuntu22 and Ubuntu24 based docker images.
- Separate optimized and extended runtime docker images.
- Publisher for InfluxDB to store metadata.
- OPC UA is now configurable in REST request.
- Improved logging by consuming log levels from `.env` instead of from `config.json`.
- WebRTC bitrate is now configurable.
- Logs can be queried and monitored in real time with Open Telemetry.
- ROS2 publisher for sending metadata (with or without encoded frames).
- Enabled VA-API based pipelines for RTSP and WebRTC streaming.

**Fixed:**

- Cleanup: Remove confidential info such as email and gitlab links. Removed unused model downloader tool, gRPC interface.
- Bug in appsink synchronization behavior not being consistent with gstreamer/DL Streamer.
- Bug in appsink destination and publisher configurations.
- WebRTC with GPU inferencing falls back to CPU if vah264enc is missing.

**Updated:**

- DL Streamer updated to 2025.1.2.
- Interface to Model registry updated with environment variables instead of `config.json`.
- Documentation updates: Cross stream batching, latency tracing, tutorial on launching and managing pipelines.

## v3.0.0

**Release Date:** April 2025

**Updated:**

- Rebranded Edge Video Analytics Microservice (EVAM) to Deep Learning Streamer Pipeline Server (DL Streamer Pipeline Server).

## v2.4.0

**Release Date:** March 2025

**Added:**

- Enabled frame publishing over WebRTC protocol to a MediaMTX server.
- New REST API to get pipeline instance status: `GET/pipelines/{instance_id}/status`.

**Fixed:**

- Fixes in model update flow.
- Fixed an issue where overlay was improper for published frames when source has I420 image format.

**Updated:**

- DLS upgraded to 2025.0.1.2.
- Geti™ SDK upgraded to version 2.7.1, sample model files updated.
- RTSP and WebRTC allows watermark overlay on frames using REST.
- Updated documentation.

## v2.3.0

**Release Date:** March 2025

**Added:**

- Image blob write support for S3 API compliant storage.
- Metadata and image blob (optional) publish support over OPC UA protocol.
- OpenTelemetry support to publish gathered metrics to Open Telemetry collector.
- MRaaS model update support for non-Intel® Geti™ models (YOLO and OMZ) loaded through gva DL Streamer elements that perform inference.
- Optimized docker image size - removed unused libraries.

**Fixed:**

- Warnings from OpenVINO™ telemetry.

**Updated:**

- DL Streamer updated to 2025.0.1.
- Updated third party programs list for components with copyleft licenses.
- Updated documentation.

## v2.2.0

**Release Date:** February 2025

**Added:**

- Support for synchronous REST API, timeout and base64 image in Image Ingestor.
- MRaaS support in Helm chart.
- Support for NV12 and I420 image formats in EVAM Publisher.
- Option to send frames optionally in image ingestion REST API requests.
- Payload support in config when auto-start is enabled.
- Insourced pipeline server.

**Fixed:**

- Bug in Geti™ UDF loader's color space handling.
- Bug in not being able to run multiple instances simultaneously of the same pipeline on dGPU and iGPU.
- Bug in allowing to re-run pipeline with a failed model-instance-id.

**Updated:**

- DL Streamer updated to 2025.0.0.
- Geti™ SDK updated to version 2.5.0.
- Updated documentation, license, copyright.
