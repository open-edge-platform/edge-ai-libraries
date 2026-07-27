# Release Notes: DL Streamer Pipeline Server

<!--## Version 2026.2.0-->

<!--date TBD-->

## Version 2026.1.0

**Release Date:** June 17, 2026

**New:**

- Added an exemplary pipeline configuration for NPU decode-and-inference (pallet_defect_detection pipeline using `1VA-API H.264` decode and gvadetect targeting the NPU device).

**Improved:**

- Updated the base Docker image from `intel/dlstreamer:2025.2.0-ubuntu22` to `intel/dlstreamer:2026.0.0-ubuntu24`. The default published image is now Ubuntu 24.
- Updated the bundled OpenVINO™ Python package to 2026.0.0.
- Replaced hardcoded render group IDs (109, 110, 992) in all Docker Compose files with a single configurable `RENDER_GID` environment variable, simplifying GPU/NPU device access across different host operating systems.
- Improved Swagger/OpenAPI documentation formatting and readability for all REST API endpoints.
- Graceful GStreamer pipeline shutdown: pipelines now terminate cleanly with improved shutdown logging.

**Fixed:**

- Fixed a memory leak in the `latency_times` dictionary where per-pipeline entries accumulated indefinitely.
- Replaced the `x264enc H.264` encoder with `openh264enc` in the WebRTC streaming path, removing a GPL-licensed codec dependency.

## Previous Releases

- [Release Notes 2025](./release-notes/release-notes-2025.md)
- [Release Notes 2024](./release-notes/release-notes-2024.md)

<!--hide_directive
:::{toctree}
:hidden:

Release Notes 2025 <release-notes/release-notes-2025.md>
Release Notes 2024 <release-notes/release-notes-2024.md>

:::
hide_directive-->
