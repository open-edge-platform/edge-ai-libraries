# Release Notes: DL Streamer Pipeline Server 2024

## v2.1.0

**Release Date:** November 2024

**Added:**

- Annotation overlay support for clients.
- Support for mTLS and configurable gRPC in EVAM.
- Option to disable LEM check.
- Time field to gvapython MQTT publisher and Geti™ wrapper.
- Multi-threaded client publishers for performance improvements.
- Standalone EVAM Helm chart.
- Optimizations to Dockerfile for lean Docker image size.

**Fixed:**

- Bug where missing UDFs would cause task key errors.
- Issue where multiple pipeline instances would not refer to their own data.
- Expired Model Registry Microservice JWT handling in EVAM.
- Hard coded visualization overlay for classification models.
- Error for REST requests with no metadata.
- Volume mount permissions for deployments.
- Overlay persistence bug for classification UDFs.
- Removed encoded Geti™ prediction from metadata.

**Updated:**

- DL Streamer updated to 2024.2.0.
- Removed deprecated pipeline size checks for client list size.
- Updated documentation.

## v2.0.0

**Release Date:** November 2024

**Added:**

- Support for image file ingestor and RGB frame format in UDF plugin.
- Capability to load models from the Model Registry Microservice during EVAM startup.
- New REST API endpoint for model downloading.
- gRPC integration for communication.
- SSL (HTTPS) support for serving traffic.
- Restructured the repository and refactored code for ease of maintenance.
- Enabled API to get pipeline instance summary.

**Fixed:**

- Updated exception handling across the code base.
- Issues with Model Registry integration.
- Improved error handling for self-signed TLS certificate generation script.

**Updated:**

- Enhanced ModelRegistryClient and simplified interactions with the Model Registry.
- Geti™ SDK upgraded to version 2.2.0.
- DL Streamer updated to 2024.1.0.

## v1.3.2

**Release Date:** October 2024

**Updated:**

- Updated setuptools version.

## v1.3.1

**Release Date:** September 2024

**Updated:**

- Updates to XIRIS app, adding support for additional configuration parameters.
- Minor bug fixes and improvements.
- Documentation updates for clarity and completeness.

## v1.3.0

**Release Date:** July 2024

**Added:**

- Object tracking functionality for UDFs.
- Tags to published metadata.
- Improved gencamsrc handling of default property values.

**Fixed:**

- Issues with image format handling (in gencamsrc) and NPU driver updates.

**Updated:**

- DL Streamer updated to version 2024.0.2.
- Updated ONNX and OpenVINO™ pip packages.
- Documentation updates.
