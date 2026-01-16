# February 2025

## v2.2.0

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
- DL Streamer updated to 2025.0.0.
- Geti SDK updated to version 2.5.0.
- Updated documentation, license, copyright.