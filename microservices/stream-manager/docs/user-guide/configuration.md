<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Configuration

Stream Manager works out of the box with built-in default settings. You do not need
a `config.json` file to run it.

To change a setting, create a `config.json` file. You only need to list the settings
you want to change. Stream Manager uses its default value for any setting you leave out.

You can also start from the sample `config.json` file in the repository root. Copy it,
then edit only the values you need.

Stream Manager stops startup if the file contains invalid JSON or a value with the
wrong type. If the file is missing or cannot be read, it logs a warning and uses
the built-in defaults. It ignores unknown field names.

This page lists each setting, its purpose, and its default value.

## config.json fields

| Field | Type | Unit | Default | Purpose |
| --- | --- | --- | --- | --- |
| `HTTPAddr` | string | — | `:8080` | Address and port the HTTP server listens on. |
| `BufferLength` | integer | seconds | `30` | Default rolling buffer length for a new stream. A request to `POST /streams` can override this per stream. Must be between 5 and 300. |
| `StorageDir` | string | — | `~/.local/share/stream-manager` | Directory for the database and recordings. The service user must own the directory. Use mode `0700` to prevent group and other users from accessing it. |
| `ConcurrentRecorders` | integer | count | `15` | Maximum number of recordings that can run at the same time. Must be between 1 and 1024. |
| `RecordingStorageSize` | integer | GiB | `10` | Storage quota for recorded media and the frames and clips extracted from it. Must be between 5 and 102400 (5 GiB to 100 TiB). |

## Example

```json
{
  "HTTPAddr": "0.0.0.0:8080",
  "BufferLength": 30,
  "StorageDir": "~/.local/share/stream-manager",
  "ConcurrentRecorders": 15,
  "RecordingStorageSize": 10
}
```

### Where Stream Manager looks for config.json

By default, Stream Manager reads `config.json` from the current directory.
Use the options described in the following sections to select a different file.

## Host run options

When you build from source, use this option with `make run` or `make start`:

| Option | Purpose |
| --- | --- |
| `CONFIG_FILE` | Select a custom configuration file instead of the default `config.json`. |

```bash
make run CONFIG_FILE=/path/to/config.json
```

If you omit `CONFIG_FILE`, these Make targets use the default configuration file.

See [Build From Source](build-from-source.md) for build instructions
and instructions to run the application on the host.

## Container run options

Use these options with `make docker-run`:

| Option | Purpose | Default |
| --- | --- | --- |
| `IMAGE` | Container image name and tag. | `intel/stream-manager:latest` |
| `CONFIG_FILE` | Host configuration file mounted at `/config.json` (read-only). | Empty (uses built-in defaults). |
| `DATA_DIR` | Host directory mounted at `/data` instead of a Docker volume. | Empty (a default Docker volume is used). |
| `CONTAINER_NAME` | Container name. | `stream-manager` |

```bash
make docker-run DATA_DIR=/path/to/data CONFIG_FILE=/path/to/config.json
```

`make docker-run` pulls the image if it is not present locally. It stops and removes
any existing container with the same name before it starts a new one. It publishes the
container's port `8080` to a free host port and prints the access URLs.

> [!CAUTION]
> When you set `DATA_DIR`, `make docker-run` changes the ownership of the selected
> directory. This can require `sudo` access.
> Select a directory only for Stream Manager data.

> [!NOTE]
> When `DATA_DIR` is empty, `make docker-run` uses the Docker volume named `stream-manager-data`
> for persistence of application data.

### Container Default Settings

The published container image sets two environment variables. These values override
the corresponding settings in `config.json`:

| Variable | Default value |
| --- | --- |
| `SM_HTTP_ADDR` | `:8080` |
| `SM_DATA_DIR` | `/data` |

The Docker volume `stream-manager-data` or the selected host directory is mounted at `/data`
inside the container. Do not try to change the listen port or storage path through a mounted
`config.json` — it will have no effect.
To change these values, use environment overrides with `docker run`.
`make docker-run` does not provide options for these overrides.

See [Get Started](get-started.md) and [Build From Source](build-from-source.md) for how
to run Stream Manager with a custom `config.json`.
