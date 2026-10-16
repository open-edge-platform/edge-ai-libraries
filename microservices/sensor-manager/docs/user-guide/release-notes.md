# Release Notes: Sensor Manager

## Version 2026.3.0

Initial release of Sensor Manager as a camera discovery service.

**Release Date:** TBD

**New:**

- **USB and ONVIF camera discovery**: Initial release of Sensor Manager, with USB and ONVIF camera
  discovery moved out of the Visual Pipeline and Platform Evaluation Tool.
- **dlstreamer.onvif**: ONVIF discovery and media profile retrieval use the `dlstreamer.onvif`
  library.
- **REST API**: `/api/v1/sensors` REST API, Docker Compose file and Helm chart.
