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
| `ConcurrentRecorders` | integer | count | `10` | Maximum number of recordings that can run at the same time. |
| `RecordingStorageSize` | integer | megabytes | `10240` | Target storage quota for recordings. |

> [!NOTE]
> `RecordingStorageSize` is accepted and stored, but not yet enforced. Stream Manager
> does not delete old recordings to stay under this quota today. This behaviour will
> change in future updates.

## Example

```json
{
  "HTTPAddr": "0.0.0.0:8080",
  "BufferLength": 30,
  "StorageDir": "~/.local/share/stream-manager",
  "ConcurrentRecorders": 10,
  "RecordingStorageSize": 10240
}
```

## Where Stream Manager looks for config.json

By default, Stream Manager reads `config.json` from its current working directory.
Set the `SM_CONFIG_FILE` environment variable to use a file at a different path.

## Overrides inside a container

Two settings are fixed inside the published container image, and always win over
`config.json`:

| Setting | Fixed value | Set via |
| --- | --- | --- |
| `HTTPAddr` | `:8080` | `SM_HTTP_ADDR` environment variable |
| `StorageDir` | `/data` | `SM_DATA_DIR` environment variable |

Mount your own data volume or directory at `/data`, as shown in
[Get Started](get-started.md). Do not try to change the listen port or storage
path through a mounted `config.json` — it will have no effect.

See [Get Started](get-started.md) and [Build From Source](build-from-source.md) for how
to run Stream Manager with a custom `config.json`.
