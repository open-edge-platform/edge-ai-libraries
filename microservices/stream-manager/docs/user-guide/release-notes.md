<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Release Notes: Stream Manager

## Version 2026.3.0

**Release Date**: December 7, 2026

This is the initial release of Stream Manager.

**New**:

- **Stream management**: attach RTSP streams and maintain configurable rolling buffers.
- **Recording and retrieval**: record buffered and live video, then retrieve clips or frames for a selected time.
- **Storage**: store recordings locally.
- **REST API**: access the microservice through a simple REST API.

**Fixed**:

- **Configuration handling**: reject invalid configuration at startup and provide clearer storage directory errors.
