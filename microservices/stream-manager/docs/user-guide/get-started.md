<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Get Started

This guide shows you how to run Stream Manager as a container. It uses the published
image `intel/stream-manager:latest`.

## Prerequisites

- Docker, version 29.0 or later.
- `make`.
- `curl`.

## Run the application

```bash
curl -fsSL https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/stream-manager/Makefile | make -f - docker-run
```

This downloads the Makefile and runs it directly with `make`. It starts the
container, publishes its port to a free host port, and prints the application
access URLs.

Check that the application is live:

```bash
curl http://localhost:<port>/v1/status
```

A healthy response looks like this:

```json
{"status":"ok","version":"<version>","build_number":"<build>","build_date":"2026-01-01T00:00:00+0000"}
```

> [!TIP]
> Read the full API documentation at `http://localhost:<port>/docs/v1/index.html`.

Stop and remove the running container:

```bash
curl -fsSL https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/stream-manager/Makefile | make -f - docker-stop
```

> [!NOTE]
> Total memory used for buffering is limited by the container's shared memory.
> The `make` command sets a custom shared memory size of the container.
> This avoids issues of buffer failures when multiple streams are buffered simultaneously.

## Options to run the application

Set `DATA_DIR` to store data in a host directory instead of the default Docker volume:

```bash
curl -fsSL https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/stream-manager/Makefile | make -f - docker-run DATA_DIR=/path/to/data
```

> [!CAUTION]
> `DATA_DIR` changes the ownership of the selected host directory.
> This can require `sudo` access. Select a directory only for Stream Manager data.

Set `CONFIG_FILE` to use your own configuration file:

```bash
curl -fsSL https://raw.githubusercontent.com/open-edge-platform/edge-ai-libraries/main/microservices/stream-manager/Makefile | make -f - docker-run CONFIG_FILE=/path/to/config.json
```

You can use both options in the same command.
See [Container run options](configuration.md#container-run-options) for all options
and [Configuration](configuration.md#configjson-fields) for the configuration file settings.

See [API Reference](api-docs/api-reference.md) for all available endpoints.
