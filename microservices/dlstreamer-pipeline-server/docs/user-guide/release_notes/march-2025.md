# March 2025

## v2.4.0

### Added in v2.4.0
- Enabled frame publishing over WebRTC protocol to a MediaMTX server.
- New REST API to get pipeline instance status: GET/pipelines/{instance_id}/status

### Fixed in v2.4.0
- Fixes in model update flow
- Fixed an issue where overlay was improper for published frames when source has I420 image format

### Updates in v2.4.0
- DLS upgraded to 2025.0.1.2
- Geti SDK upgraded 2.7.1, sample model files updated
- RTSP and WebRTC allows watermark overlay on frames using REST
- Updated documentation

---

## v2.3.0

### Added in v2.3.0

- Image blob write support for S3 API compliant storage.
- Metadata and image blob (optional) publish support over OPCUA protocol.
- OpenTelemetry support to publish gathered metrics to Open Telemetry collector.
- MRaaS model update support for non Intel® Geti™ models (YOLO and OMZ) loaded through gva
DL Streamer elements that perform inference.
- Optimized docker image size - removed unused libraries.

### Fixed in v2.3.0

- Warnings from OpenVINO telemetry.

### Updates in v2.3.0

- DL Streamer updated to 2025.0.1.
- Updated third party programs list for components with copyleft licenses.
- Updated documentation.
