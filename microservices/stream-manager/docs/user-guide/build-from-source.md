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
  --branch feat/stream-record-routers \
  https://github.com/krish918/edge-ai-libraries.git
cd edge-ai-libraries
git sparse-checkout set --cone microservices/stream-manager
git checkout
cd microservices/stream-manager
```

> [!NOTE]
> This guide uses the `feat/stream-record-routers` branch for now. It will change to
> the `main` branch after this work merges upstream.

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

The application reads `config.json` from the current directory by default, if present.
To use a file at a different path, set the `SM_CONFIG_FILE` environment variable before
running the binary. See [Configuration](configuration.md) for all available settings.

## Build and run a container image

Build the image:

```bash
make docker-build
```

The default image is `intel/stream-manager:latest`. To use a different image name or tag. For example:

```bash
make docker-build IMAGE=my-registry/stream-manager:v1-dev
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
make docker-run IMAGE=my-registry/stream-manager:v1.2.3
```

> [!NOTE]
> `make docker-run` pulls the image if it is not present locally.
> If you do not set `IMAGE`, it pulls and runs the default image.

### Container run options

| Variable | Purpose | Default |
| --- | --- | --- |
| `IMAGE` | Image name, optionally with `:tag` | `intel/stream-manager:latest` |
| `CONTAINER_NAME` | Name assigned to the container | `stream-manager` |
| `DATA_VOLUME` | Docker volume mounted at `/data` when `DATA_DIR` is empty | `stream-manager-data` |
| `DATA_DIR` | Host directory bind-mounted at `/data`, instead of `DATA_VOLUME` | Empty (uses `DATA_VOLUME`) |
| `CONFIG_FILE` | Host config file mounted at `/config.json` | Empty (uses built-in defaults) |

`make docker-run` publishes the container's port `8080` to a random host port.
It prints the assigned port and the application and API docs URLs after it starts.

An example run with the default image, an overridden `DATA_DIR`, and `CONFIG_FILE`:

```bash
make docker-run DATA_DIR=/path/to/data CONFIG_FILE=/path/to/config.json
```

See [Configuration](configuration.md) for all settings you can put in `config.json`.

> [!CAUTION]
> When you set `DATA_DIR`, the target changes ownership of that directory.
> This might require `sudo` access.
> Only point it at a directory meant for this application's data.

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
