<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Stream Manager

<!--hide_directive
<div class="component_card_widget">
  <a class="icon_github" href="https://github.com/open-edge-platform/edge-ai-libraries/tree/main/microservices/stream-manager">
     GitHub
  </a>
  <a class="icon_document" href="https://github.com/open-edge-platform/edge-ai-libraries/blob/main/microservices/stream-manager/README.md">
     Readme
  </a>
</div>
hide_directive-->

Stream Manager is a microservice for Intel Open Edge Platform. It attaches RTSP video streams,
keeps a rolling buffer of each stream, and records video on request. It also returns clips and
frames from a recording for a given time range.

## Quick Start

### Prerequisites

- **Operating system**: Ubuntu 22.04 LTS or later (this guide was tested on Ubuntu 22.04.5 LTS).
- **Docker**: version 29.0 or later (this guide was tested on Docker 29.4.3).

The simplest way to run Stream Manager is to pull and run its pre-built image.

```bash
docker run -d --name stream-manager -p 49173:8080 \
  -v stream-manager-data:/data \
  intel/stream-manager:latest
```

Once the command succeeds, you can access the API status and docs here:

Status: http://localhost:49173/v1/status

API docs: http://localhost:49173/docs/v1/index.html

> [!Note]
> Port `49173` might already be in use on your machine. If so, `docker run` fails.
> Pick a free port. Replace `49173` in the command and the URLs above with it.

## Documentation

- [Get Started](get-started.md): Run the application as a container.
- [Configuration](configuration.md): All `config.json` settings and their defaults.
- [API Reference](api-docs/api-reference.md): All REST API endpoints.
- [Build From Source](build-from-source.md): Build and run on a host or as a container image.

## Third-party Sources

Stream Manager includes FFmpeg and other third-party libraries.
A separate source image is provided which contains source archives, license notices,
and build records. See [Third-Party Sources](third-party-sources.md)
to learn how to access this source image and the bundled source code files.


<!--hide_directive
:::{toctree}
:hidden:

get-started
build-from-source
configuration
api-docs/api-reference

:::
hide_directive-->
