<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Stream Manager

Stream Manager is a microservice responsible for managing streaming video sources within the Edge AI platform.
This is a REST API based microservice that attaches  live streaming sources, keeps bounded per-stream history in memory,
saves requested intervals and returns timestamp-correlated clips and frames.

# Quick Start

__**[WIP] This section will contain the details of the simplest way possible (probably one-click) to launch the Stream Manager microservice.**__

## Overview

### Stream APIs
The stream APIs attach RTSP/RTSPS video, manage rolling buffers, report
their status, and detach them. Buffer resizing is not implemented yet.

### Recording APIs
Recording endpoints persist metadata in SQLite and save fixed or open recordings
under UUID-named directories on the local filesystem. Overlapping recordings share
buffered footage through bounded reader leases.

### Replay APIs
Replay APIs allow clients to request and retrieve previously recorded video clips or frames based on timestamps, leveraging the buffered footage and stored recordings.

See [Get Started](docs/user-guide/get-started.md) for configuration and usage.

## Project Status

| Area | Status |
| --- | --- |
| API Contract | Ready |
| Design | Ready |
| Implementation | Work in Progress |
| Documentation | Work in Progress |
