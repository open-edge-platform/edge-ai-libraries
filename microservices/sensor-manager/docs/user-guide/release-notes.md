# Release Notes: Sensor Manager

## Version 2026.3.0

Initial release of Sensor Manager as a camera discovery service.

**Release Date:** TBD

**New:**

- **USB and ONVIF camera discovery**: Initial release of Sensor Manager, with USB and ONVIF camera
  discovery moved out of the Visual Pipeline and Platform Evaluation Tool.
- **dlstreamer.onvif**: ONVIF discovery and media profile retrieval use the `dlstreamer.onvif`
  library.
- **GigE Vision camera discovery**: GigE Vision cameras are discovered with the Aravis
  `arv-tool-0.8` utility and reported as `GIGE` sensors with their vendor, model, serial number
  and current acquisition settings.
- **REST API**: `/api/v1/sensors` REST API, Docker Compose file and Helm chart.
