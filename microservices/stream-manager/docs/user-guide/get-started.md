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
curl -fsSL https://raw.githubusercontent.com/krish918/edge-ai-libraries/feat/stream-record-routers/microservices/stream-manager/Makefile | make -f - docker-run
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
{"status":"ok","version":"v1.0.0","build_number":"42","build_date":"2026-01-01T00:00:00+0000"}
```

> [!TIP]
> Read the full API documentation at `http://localhost:<port>/docs/v1/index.html`.

Stop and remove the running container:

```bash
curl -fsSL https://raw.githubusercontent.com/krish918/edge-ai-libraries/feat/stream-record-routers/microservices/stream-manager/Makefile | make -f - docker-stop
```

> [!NOTE]
> Total memory used for buffering is limited by the container's shared memory.
> The `make` command sets a custom shared memory size of the container.
> This avoids issues of buffer failures when multiple streams are buffered simultaneously.

## Keep your data on the host

By default, the above setup stores all data in a Docker volume. To use a host
directory instead, set `DATA_DIR`:

```bash
curl -fsSL https://raw.githubusercontent.com/krish918/edge-ai-libraries/feat/stream-record-routers/microservices/stream-manager/Makefile | make -f - docker-run DATA_DIR=/path/to/data/dir
```

> [!NOTE]
> `make` changes the ownership of the directory you bind-mount, so the application can
> write to it. This needs `sudo` access. Enter your password if asked.

## Use your own configuration file

Set `CONFIG_FILE` to mount your `config.json` over the default one:

```bash
curl -fsSL https://raw.githubusercontent.com/krish918/edge-ai-libraries/feat/stream-record-routers/microservices/stream-manager/Makefile | make -f - docker-run CONFIG_FILE=/path/to/config.json
```

See [Configuration](configuration.md) for all settings you can put in `config.json`.

See [API Reference](api-docs/api-reference.md) for all available endpoints.
