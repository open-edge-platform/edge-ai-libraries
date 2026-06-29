# Release Notes

## Version: 2026.1.0

**June 17, 2026**

**New**

- Added an exemplary pipeline configuration for NPU decode-and-inference (pallet_defect_detection pipeline using `1VA-API H.264` decode and gvadetect targeting the NPU device).

**Improved**

- Updated the base Docker image from `intel/dlstreamer:2025.2.0-ubuntu22` to `intel/dlstreamer:2026.0.0-ubuntu24`. The default published image is now Ubuntu 24.
- Updated the bundled OpenVINO Python package to 2026.0.0.
- Replaced hardcoded render group IDs (109, 110, 992) in all Docker Compose files with a single configurable `RENDER_GID` environment variable, simplifying GPU/NPU device access across different host operating systems.
- Improved Swagger/OpenAPI documentation formatting and readability for all REST API endpoints.
- Graceful GStreamer pipeline shutdown: pipelines now terminate cleanly with improved shutdown logging.

**Fixed**

- Fixed a memory leak in the `latency_times` dictionary where per-pipeline entries accumulated indefinitely.
- Replaced the `x264enc H.264` encoder with `openh264enc` in the WebRTC streaming path, removing a GPL-licensed codec dependency.

- [December 2025](./release-notes/december-2025.md)
- [August 2025](./release-notes/august-2025.md)
- [April 2025](./release-notes/april-2025.md)
- [March 2025](./release-notes/march-2025.md)
- [February 2025](./release-notes/february-2025.md)
- [November 2024](./release-notes/november-2024.md)
- [October 2024](./release-notes/october-2024.md)
- [September 2024](./release-notes/september-2024.md)
- [July 2024](./release-notes/july-2024.md)

<!--hide_directive

:::{toctree}
:hidden:

./release-notes/december-2025.md
./release-notes/august-2025.md
./release-notes/april-2025.md
./release-notes/march-2025.md
./release-notes/february-2025.md
./release-notes/november-2024.md
./release-notes/october-2024.md
./release-notes/september-2024.md
./release-notes/july-2024.md
:::

hide_directive-->
