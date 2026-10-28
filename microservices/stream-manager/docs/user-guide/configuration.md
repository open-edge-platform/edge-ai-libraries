<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Configuration

Stream Manager works out of the box with built-in default settings. You do not need
a `config.json` file to run it.

To change a setting, create a `config.json` file. You only need to list the settings
you want to change. Stream Manager uses its default value for any setting you leave out.

You can also start from the sample `config.json` file in the repository root. Copy it,
then edit only the values you need.

This page lists each setting, its purpose, and its default value.

## config.json fields

| Field | Type | Unit | Default | Purpose |
| --- | --- | --- | --- | --- |
| `HTTPAddr` | string | — | `:8080` | Address and port the HTTP server listens on. |
| `BufferLength` | integer | seconds | `30` | Default rolling buffer length for a new stream. A request to `POST /streams` can override this per stream. Must be between 5 and 300. |
| `StorageDir` | string | — | `~/.local/share/stream-manager` | Directory where the database and recordings are stored. |
| `ConcurrentRecorders` | integer | count | `15` | Maximum number of recordings that can run at the same time. |
| `RecordingStorageSize` | integer | gigabytes | `10` | Storage quota for recorded media and the frames and clips extracted from it. Must be between 5 and 102400. |

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
This can be changed using different options described in next sections.

## Host run options

When you build from source, use this option with `make run` or `make start`:

| Option | Purpose |
| --- | --- |
| `CONFIG_FILE` | Select a custom configuration file instead of default `config.json`. |

```bash
make run CONFIG_FILE=/path/to/config.json
```

If you omit `CONFIG_FILE`, default configuration file is used.
See [Build From Source](build-from-source.md) for build instructions
and running application on host.

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

`make docker-run` pulls the image if it is not present locally. It publishes the
container's port `8080` to a free host port and prints the access URLs.

> [!CAUTION]
> When you set `DATA_DIR`, `make docker-run` changes the ownership of the selected
> directory. This can require `sudo` access.
> Select a directory only for Stream Manager data.

> [!NOTE]
> When `DATA_DIR` is empty, `make docker-run` uses the Docker volume named `stream-manager-data`
> for persistence of application data.

### Container Default Settings

Two settings are defined inside the published container image, and always have precedence
over `config.json`:

| Setting | Fixed value |
| --- | --- |
| `HTTPAddr` | `:8080` |
| `StorageDir` | `/data` |

The Docker volume `stream-manager-data` or the selected host directory is mounted at `/data`
inside the container. Do not try to change the listen port or storage path through a mounted
`config.json` — it will have no effect.

See [Get Started](get-started.md) and [Build From Source](build-from-source.md) for how
to run Stream Manager with a custom `config.json`.
