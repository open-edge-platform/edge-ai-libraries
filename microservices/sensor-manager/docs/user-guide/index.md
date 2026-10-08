# Sensor Manager

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/sensor-manager">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/sensor-manager/README.md">
     Readme
  </a>
</div>
hide_directive-->

Sensor Manager discovers the cameras available to an edge node and exposes them through a REST
API, so that applications such as the Visual Pipeline and Platform Evaluation Tool (ViPPET) can
build GStreamer pipelines for them without implementing device discovery themselves.

## Components

- **REST API** (FastAPI) – `/api/v1/sensors` endpoints and OpenAPI documentation at `/docs`.
- **USB discovery** – runs `v4l2-ctl --list-devices`, keeps only devices that report the
  `Video Capture` capability and scores all supported `(format, resolution, fps)` combinations to
  select the best capture configuration (H.264/H.265 > MJPEG > raw, target 1920x1080 at 30 fps,
  at least 15 fps preferred).
- **ONVIF discovery** – a background thread runs a WS-Discovery sweep
  (`dlstreamer.onvif.discover_onvif_cameras`) every `ONVIF_DISCOVERY_INTERVAL_S` seconds.
  Cameras that do not answer a sweep are removed from the list.
- **ONVIF profiles** – on request, the service reads media profiles with
  `dlstreamer.onvif.read_camera_profiles` using the supplied credentials and selects the best
  profile with the same scoring as for USB cameras. Loaded profiles are cached for as long as the
  camera stays discovered.

Camera credentials are used only for the profile request. They are not stored, logged or
returned by the service; clients that open RTSP streams must keep them on their side.

## Sensor identifiers

| Type | Identifier | Example |
|------|------------|---------|
| USB | `usb-camera-{slugified device name}-{video device number}` | `usb-camera-integrated-camera-0` |
| ONVIF | `network-camera-{host}-{port}` | `network-camera-192.168.1.100-80` |

## Learn More

- [Get Started](./get-started.md)
- [API Reference](./api-reference.md)
- [Release Notes](./release-notes.md)

<!--hide_directive
:::{toctree}
:hidden:

./get-started.md
./api-reference.md
Release Notes <./release-notes.md>

:::
hide_directive-->
