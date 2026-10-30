<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Build From Source

This guide shows you how to build Stream Manager from source. You can build a binary
for your host, or a container image.

## Prerequisites

- Go 1.26 or later (for host builds).
- Docker 29.0 or later (for container builds).
- `make`.
- `git`.

## Get the source code

This repository holds many projects. Use a sparse checkout to download only the
`stream-manager` project, on a single branch:

```bash
git clone --no-checkout --filter=blob:none --single-branch \
  --branch main \
  https://github.com/open-edge-platform/edge-ai-libraries.git
cd edge-ai-libraries
git sparse-checkout set --cone microservices/stream-manager
git checkout
cd microservices/stream-manager
```

All other commands in this guide run from this `stream-manager` directory.

## Build and run on your host

Build the application binary:

```bash
make build
```

Run the binary you just built:

```bash
make run
```

Or do both in one step:

```bash
make start
```

To use your own configuration file:

```bash
make run CONFIG_FILE=/path/to/config.json
```

See [Host run options](configuration.md#host-run-options) for defaults and
host data directory settings.

## Build and run a container image

Build the image:

```bash
make docker-build
```

The default image is `intel/stream-manager:latest`. To use a different image name or tag. For example:

```bash
make docker-build IMAGE=<your_image_name>:<tag>
```

> [!NOTE]
> The image contains FFmpeg license files, notices, version information, and
> checksums in `/usr/share/licenses/ffmpeg/`.
> The image keeps the base image's license files in `/usr/share/common-licenses/`
> and `/usr/share/doc/`.

> [!IMPORTANT]
> The third-party source archives are provided in a separate source image.
> See [Third-Party Sources](third-party-sources.md) for instructions to copy the
> FFmpeg, its dependencies, and base image source files.

Run the image you built, or a published image you already have:

```bash
make docker-run IMAGE=<your_image_name>:<tag>
```

> [!NOTE]
> `make docker-run` pulls the image if it is not present locally.
> If you do not set `IMAGE`, it pulls and runs
> the default image i.e. `intel/stream-manager:latest`.

`make docker-run` publishes the container's port `8080` to a random host port.
It prints the assigned port and the application and API docs URLs after it starts.

See [Container run options](configuration.md#container-run-options) for configuration
file and data mount options.

Stop and remove the running container:

```bash
make docker-stop
```

Remove built host binaries (keeps the `./bin` directory):

```bash
make clean
```

See [Get Started](get-started.md) for how to use the running application, and
[API Reference](api-docs/api-reference.md) for all endpoints.
