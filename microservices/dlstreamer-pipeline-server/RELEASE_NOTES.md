# Release Notes

## v2.3.0 (March 2025)

### Added
- Image blob write support for S3 API compliant storage.
- Metadata and image blob (optional) publish support over OPCUA protocol.
- OpenTelemetry support to publish gathered metrics to Open Telemetry collector.
- MRaaS model update support for non Intel® Geti™ models (YOLO and OMZ) loaded through gva DLStreamer elements that perform inference.
- Optimized docker image size - removed unused libraries.

### Fixed
- Warnings from OpenVINO telemetry.

### Updates
- DLStreamer updated to 2025.0.1.
- Updated third party programs list for components with copyleft licenses.
- Updated documentation.

---

## v2.2.0 (February 2025)

### Added
- Support for synchronous REST API, timeout and base64 image in Image Ingestor.
- MRaaS support in Helm chart.
- Support for NV12 and I420 image formats in EVAM Publisher.
- Option to send frames optionally in image ingestion REST API requests.
- Payload support in config when auto-start is enabled.
- Insourced pipeline server.

### Fixed
- Bug in Geti UDF loader's color space handling.
- Bug in not being able to run multiple instances simultaneously of the same pipeline on dGPU and iGPU.
- Bug in allowing to re-run pipeline with a failed model-instance-id. 

### Updates
- DLStreamer updated to 2025.0.0.
- Geti SDK updated to version 2.5.0.
- Updated documentation, license, copyright.

---

## v2.1.0 (November 2024)

### Added
- Annotation overlay support for clients.
- Support for mTLS and configurable gRPC in EVAM.
- Option to disable LEM check.
- Time field to gvapython mqtt publisher and Geti wrapper.
- Multi-threaded client publishers for performance improvements.
- Standalone EVAM Helm chart.
- Optimizations to Dockerfile for lean docker image size.

### Fixed
- Bug where missing UDFs would cause task key errors.
- Issue where multiple pipeline instances wouldn't refer to their own data.
- Expired Model Registry Microservice JWT handling in EVAM.
- Hardcoded visualization overlay for classification models.
- Error for REST requests with no metadata.
- Volume mount permissions for deployments.
- Overlay persistence bug for classification UDFs.
- Removed encoded geti prediction from metadata

### Updates
- DLStreamer updated to 2024.2.0.
- Removed deprecated pipeline size checks for client list size.
- Updated documentation.

---

## v2.0.0 (November 2024)

### Added
- Support for image file ingestor and RGB frame format in UDF plugin.
- Capability to load models from the Model Registry Microservice during EVAM startup.
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
- DLStreamer updated to 2024.1.0.

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
- DLStreamer updated to version 2024.0.2.
- Updated ONNX and OpenVINO pip packages.
- Documentation updates.
