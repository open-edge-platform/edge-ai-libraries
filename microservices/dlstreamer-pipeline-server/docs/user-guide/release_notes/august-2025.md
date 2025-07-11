# August 2025 (Upcoming release)

## v3.1.0

### Added
- Support for Ubuntu22 and Ubuntu24 based docker images
- Separate optimized and extended runtime docker images
- Publisher for InfluxDB to store metadata
- OPCUA is now configurable in REST request
- Improved logging by consuming log levels from .env instead of from config.json
- WebRTC bitrate is now configurable
- Logs can be queried and monitored in real time with Open Telemetry
- ROS2 publisher for sending metadata (with or without encoded frames)

### Fixed
- Cleanup: Remove confidential info such as email and gitlab links. Removed unused model downloader tool, gRPC interface
- Bug in appsink synchronization behavior not being consistent with gstreamer/DL Streamer
- Bug in appsink destination and publisher configurations

### Updates
- DL Streamer updated to TBD
- Interface to Model registry updated with environment variables instead of config.json
- Documentation updates: Cross stream batching, latency tracing, tutorial on launching and managing pipelines