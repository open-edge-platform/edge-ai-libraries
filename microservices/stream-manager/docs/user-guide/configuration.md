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
| `RecordingStorageSize` | integer | megabytes | `10240` | Storage quota for recorded media and the frames and clips cut from it. Must be between 5120 and 1073741824. |
| `RecordingRetention` | integer | hours | `0` | Time to keep a finished or failed recording. Stream Manager then deletes the recording and its media. `0` keeps recordings until you delete them. Must be between 0 and 87600. |
| `DerivedMediaTTL` | integer | minutes | `-1` | Time to keep a frame or clip after Stream Manager cuts it. Set to `-1` to disable the TTL. Otherwise, use a value between 1 and 1440. |

### Storage quota

Stream Manager counts the bytes of each recording and of its frames and clips.

- When the quota is full, `POST /records/start` returns `507` with `storage_full`.
- When a running recording fills the quota, the recording stops early with the state
  `ready`. `end_ts` is the end of the last saved video. `error_detail` is
  `truncated: recording storage quota reached`.
- When a recording fills the quota before it saves video, the recording stops with the
  state `failed`. Stream Manager deletes its media.
- When the quota is full, a new frame or clip request returns `507` with `storage_full`.

Stream Manager does not delete old recordings to make space. To make space, delete
recordings or set `RecordingRetention`.

> [!NOTE]
> The quota does not include the database file. A recording can go above the quota by
> a small amount when FFmpeg finishes the file.

### Recording retention

When `RecordingRetention` is more than `0`, Stream Manager sets `expiry_ts` on each
recording when the recording becomes `ready` or `failed`. Stream Manager checks for
expired recordings at startup and every 24 hours, then deletes them. Retrieve requests
for an expired recording return `404`.

The same cleanup job removes recording folders that have no metadata, including media
left after a delete request. Media in use is kept until a later cleanup.

If you change `RecordingRetention` to `0`, new recordings get no `expiry_ts`.
Stream Manager continues to delete the recordings that already have an `expiry_ts`.

> [!CAUTION]
> Stream Manager deletes expired recordings permanently. Set `RecordingRetention` only
> when you do not need the recordings after this time.

### Frame and clip lifetime

When `DerivedMediaTTL` is greater than `0`, Stream Manager keeps each frame and clip
for that many minutes. A request for the same frame or clip during this time gets the
saved file. After this time, the `url` in the `MediaResult` returns `404`, and a new
request cuts the frame or clip again.

Set `DerivedMediaTTL` to `-1` to disable this expiry. The URL then stays available
until the recording expires or you delete the recording. When neither expiry applies,
`expiry_ts` is `null`.

> [!NOTE]
> A frame or clip never stays longer than its recording. When the recording has an
> earlier `expiry_ts`, the frame or clip uses that time.

## Example

```json
{
  "HTTPAddr": "0.0.0.0:8080",
  "BufferLength": 30,
  "StorageDir": "~/.local/share/stream-manager",
  "ConcurrentRecorders": 10,
  "RecordingStorageSize": 10240,
  "RecordingRetention": 0,
  "DerivedMediaTTL": -1
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
