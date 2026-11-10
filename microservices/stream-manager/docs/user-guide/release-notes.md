<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Release Notes: Stream Manager

## Version 2026.3.0-rc1

**Release Date**: November, 2026

This first release introduces **RTSP stream buffering**, **video recording**, and **time-based clip and frame retrieval**, with local storage using a simple REST API microservice.

**New**

- **Stream management**: attach RTSP streams and maintain configurable rolling buffers.
- **Recording and retrieval**: record buffered and live video, then retrieve clips or frames for a selected time.
- **Storage**: store recordings locally.

**Fixed**

- **Configuration handling**: reject invalid configuration at startup and provide clearer storage directory errors.
