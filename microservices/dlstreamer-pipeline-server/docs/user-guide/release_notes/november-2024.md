# November 2024

## v2.1.0

### Added in v2.1.0
- Annotation overlay support for clients.
- Support for mTLS and configurable gRPC in EVAM.
- Option to disable LEM check.
- Time field to gvapython mqtt publisher and Geti wrapper.
- Multi-threaded client publishers for performance improvements.
- Standalone EVAM Helm chart.
- Optimizations to Dockerfile for lean docker image size.

### Fixed in v2.1.0
- Bug where missing UDFs would cause task key errors.
- Issue where multiple pipeline instances would not refer to their own data.
- Expired Model Registry Microservice JWT handling in EVAM.
- Hard coded visualization overlay for classification models.
- Error for REST requests with no metadata.
- Volume mount permissions for deployments.
- Overlay persistence bug for classification UDFs.
- Removed encoded geti prediction from metadata

### Updates in v2.1.0
- DL Streamer updated to 2024.2.0.
- Removed deprecated pipeline size checks for client list size.
- Updated documentation.

---

## v2.0.0

### Added in v2.0.0
- Support for image file ingestor and RGB frame format in UDF plugin.
- Capability to load models from the Model Registry Microservice during EVAM startup.
- New REST API endpoint for model downloading.
- gRPC integration for communication.
- SSL (HTTPS) support for serving traffic.
- Restructured repo and refactored code for ease of maintenance.
- Enabled API to get pipeline instance summary.

### Fixed in v2.0.0
- Updated exception handling across the code base.
- Issues with Model Registry integration.
- Improved error handling for self-signed TLS certificate generation script.

### Updates in v2.0.0
- Enhanced ModelRegistryClient and simplified interactions with the Model Registry.
- Geti SDK upgraded to version 2.2.0.
- DL Streamer updated to 2024.1.0.