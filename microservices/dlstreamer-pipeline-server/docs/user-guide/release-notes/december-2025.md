# December 2025

## Version: 2025.2.0

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