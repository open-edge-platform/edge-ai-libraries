# Release Notes

## Version: 2025.2.0 (December 2025)

### Added
- `souphttpsrc` element in docker file.

### Fixed
- Wrong formatting in compose file
- Added missing eis_mqtt_publish_doc.md documentation
- Fixed WebRTC GPU pipeline functionality for Xeon+dGPU hardware combinations
- Updated Helm chart version in documentation and dockerhub to be in sync with current one.
- Resolved issue where videoconvert was dropping tensor data provided by gvametaconvert
- Updated [Helm chart](https://hub.docker.com/layers/intel/dlstreamer-pipeline-server/2025.2.0/images/sha256-c878cc4d3606ebe242611b8ba7ffd551726c95a806e6bc415965d3f0f15a5a8f) on Dockerhub
- Incorrect communication between containers has been fixed by configuring properenv variables.
- RSTP connection error recovery mechanism


### Updates
- DL Streamer updated to 2025.2.0


---


## v3.1.0 (August 2025)

### Added
- Support for Ubuntu22 and Ubuntu24 based docker images
- Separate optimized and extended runtime docker images
- Publisher for InfluxDB to store metadata
- OPCUA is now configurable in REST request
- Improved logging by consuming log levels from .env instead of from config.json
- WebRTC bitrate is now configurable
- Logs can be queried and monitored in real time with Open Telemetry
- ROS2 publisher for sending metadata (with or without encoded frames)
- Enabled VA-API based pipelines for RTSP and WebRTC streaming

### Fixed
- Cleanup: Remove confidential info such as email and gitlab links. Removed unused model downloader tool, gRPC interface
- Bug in appsink synchronization behavior not being consistent with gstreamer/DL Streamer
- Bug in appsink destination and publisher configurations
- WebRTC with GPU inferencing falls back to CPU if vah264enc is missing.

### Updates
- DL Streamer updated to 2025.1.2
- Interface to Model registry updated with environment variables instead of config.json
- Documentation updates: Cross stream batching, latency tracing, tutorial on launching and managing pipelines

---

## v3.0.0 (April 2025)

### Updates
- Rebranded Edge Video Analytics Microservice (EVAM) to Deep Learning Streamer Pipeline Server (DL Streamer Pipeline Server).

---

## v2.4.0 (March 2025)

### Added
- Enabled frame publishing over WebRTC protocol to MediaMTX server.
- New REST API to get pipeline instance status: GET/pipelines/{instance_id}/status

### Fixed
- Fixes in model update flow
- Fixed an issue where overlay was improper for published frames when source has I420 image format

### Updates
- DLS upgraded to 2025.0.1.2
- Geti SDK upgraded 2.7.1, sample model files updated
- RTSP and WebRTC allows watermark overlay on frames using REST
- Updated documentation

---

## v2.3.0 (March 2025)

### Added
- Image blob write support for S3 API compliant storage.
- Metadata and image blob (optional) publish support over OPCUA protocol.
- OpenTelemetry support to publish gathered metrics to Open Telemetry collector.
- MRaaS model update support for non Intel® Geti™ models (YOLO and OMZ) loaded through gva DL Streamer elements that perform inference.
- Optimized docker image size - removed unused libraries.

### Fixed
- Warnings from OpenVINO telemetry.

### Updates
- DL Streamer updated to 2025.0.1.
- Updated third party programs list for components with copyleft licenses.
- Updated documentation.

---

## v2.2.0 (February 2025)

### Added
- Support for synchronous REST API, timeout and base64 image in Image Ingestor.
- MRaaS support in Helm chart.
- Support for NV12 and I420 image formats in DL Streamer Pipeline Server Publisher.
- Option to send frames optionally in image ingestion REST API requests.
- Payload support in config when auto-start is enabled.
- Insourced pipeline server.

### Fixed
- Bug in Geti UDF loader's color space handling.
- Bug in not being able to run multiple instances simultaneously of the same pipeline on dGPU and iGPU.
- Bug in allowing to re-run pipeline with a failed model-instance-id.

### Updates
- DL Streamer updated to 2025.0.0.
- Geti SDK updated to version 2.5.0.
- Updated documentation, license, copyright.

---

## v2.1.0 (November 2024)

### Added
- Annotation overlay support for clients.
- Support for mTLS and configurable gRPC in DL Streamer pipeline server.
- Option to disable LEM check.
- Time field to gvapython mqtt publisher and Geti wrapper.
- Multi-threaded client publishers for performance improvements.
- Standalone DL Streamer pipeline server Helm chart.
- Optimizations to Dockerfile for lean docker image size.

### Fixed
- Bug where missing UDFs would cause task key errors.
- Issue where multiple pipeline instances wouldn't refer to their own data.
- Expired Model Registry Microservice JWT handling in DL Streamer pipeline server.
- Hardcoded visualization overlay for classification models.
- Error for REST requests with no metadata.
- Volume mount permissions for deployments.
- Overlay persistence bug for classification UDFs.
- Removed encoded geti prediction from metadata

### Updates
- DL Streamer updated to 2024.2.0.
- Removed deprecated pipeline size checks for client list size.
- Updated documentation.

---

## v2.0.0 (November 2024)

### Added
- Support for image file ingestor and RGB frame format in UDF plugin.
- Capability to load models from the Model Registry Microservice during DL Streamer pipeline server startup.
- New REST API endpoint for model downloading.
- gRPC integration for communication.
- SSL (HTTPS) support for serving traffic.
- Restructured repo and refactored code for ease of maintenance.
- Enabled API to get pipeline instance summary.

### Fixed
- Updated exception handling across the codebase.
- Issues with Model Registry integration.
- Improved error handling for self-signed TLS certificate generation script.

### Updates
- Enhanced ModelRegistryClient and simplified interactions with the Model Registry.
- Geti SDK upgraded to version 2.2.0.
- DL Streamer updated to 2024.1.0.

---

## v1.3.2 (October 2024)

### Updates
- Updated setuptools version.

---

## v1.3.1 (September 2024)

### Updates
- Updates to XIRIS app, adding support for additional configuration parameters.
- Minor bug fixes and improvements.
- Documentation updates for clarity and completeness.

---

## v1.3.0 (July 2024)

### Added
- Object tracking functionality for UDFs.
- Tags to published metadata.
- Improved gencamsrc handling of default property values.

### Fixed
- Issues with image format handling (in gencamrsrc) and NPU driver updates.

### Updates
- DL Streamer updated to version 2024.0.2.
- Updated ONNX and OpenVINO pip packages.
- Documentation updates.
