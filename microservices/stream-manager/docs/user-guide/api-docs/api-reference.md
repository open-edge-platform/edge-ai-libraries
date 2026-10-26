<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# API Reference

This reference documents every endpoint published in [`openapi.yaml`](./openapi.yaml), with
sample requests, `curl` commands, and sample responses drawn from the current implementation.
It complements the OpenAPI specification with necessary examples and finer details.

> [!IMPORTANT]
> The service configuration can be overridden using a `config.json` file placed in the application root.
> A sample `config.json` file is already provided in the repo with default values.
> See [Configuration](../configuration.md) for all available settings.

## Table of Content

- [Base URL and versioning](#base-url-and-versioning)
- [Conventions](#conventions)
- [Common response objects](#common-response-objects)
- [Service APIs](#service-apis)
  - [Service status](#service-status)
- [Stream Attachment APIs](#stream-attachment-apis)
  - [Attach a source](#attach-a-source)
  - [List streams](#list-streams)
  - [Get a stream](#get-a-stream)
  - [Detach a stream](#detach-a-stream)
  - [Resize a stream buffer](#resize-a-stream-buffer)
- [Recording Storage APIs](#recording-storage-apis)
  - [Start a recording](#start-a-recording)
  - [Stop an open recording](#stop-an-open-recording)
  - [Find records](#find-records)
  - [Get a record](#get-a-record)
  - [Delete a record](#delete-a-record)
- [Retrieval APIs](#retrieval-apis)
  - [Extract a frame](#extract-a-frame)
  - [Get an HTTP link to a frame](#get-an-http-link-to-a-frame)
  - [Extract a clip](#extract-a-clip)
  - [Get an HTTP link to a clip](#get-an-http-link-to-a-clip)
  - [Get produced media](#get-produced-media)
- [Error code reference](#error-code-reference)

## Base URL and versioning

All endpoints are mounted under the `/v1` prefix. The service listens on `8080` port by default
(override this using the `config.json`). Examples in this document use:

```
http://localhost:8080/v1
```

## Conventions

- **Content type**: requests and responses use `application/json`, except `/retrieve/*`
  and `/media/*`, which may return raw image/video bytes (see
  [Retrieval APIs](#retrieval-apis)).
- **Timestamps**: RFC 3339, UTC, with a `Z` suffix and up to 9 fractional digits
  (nanosecond precision), for example `2026-09-16T09:12:03.400000000Z`.
- **Identifiers**: New `stream_id` values start with `str-` and contain 22 URL-safe
  characters after the prefix (26 characters total). New `recording_id` values contain
  22 URL-safe characters without a prefix. Both encode a random UUID. Existing records
  can retain their 36-character UUIDs. Treat all IDs as opaque strings. `sensor_id` is
  the name supplied by the caller. Resource IDs are 1-128 characters and match
  `^[A-Za-z0-9_-][A-Za-z0-9._:-]*$`. Sensor IDs are 1-128 characters and match
  `^[A-Za-z0-9][A-Za-z0-9._:-]*$`.
- **Pagination**: `GET /records` accepts `cursor` and `limit` (1-100, default 20) and
  returns `next_cursor`, an opaque token to pass back as `cursor` for the next page.
  `next_cursor` is `null` when there are no more pages. Stream listing is not paged.
- **Metadata filtering**: `GET /records` accepts repeated `metadata[key]=value` query
  parameters, AND-combined with every other filter.
- **Errors**: every non-2xx response returns the same [`Error`](#error) shape.

## Common response objects

> [!NOTE]
> The examples use short placeholders such as `str-1` and `rec-2`. These are not
> generated IDs. Use the IDs returned by the service in later requests.

### Error

Returned by every failure on every endpoint.

| Field | Type | Description |
|---|---|---|
| `status` | integer | The HTTP status code, repeated inside the body. |
| `error_code` | string | A short, stable code meant to be matched by software. |
| `error_detail` | string | A short explanation for a person. Never contains file paths, source addresses, credentials, or FFmpeg output. |

```json
{
  "status": 409,
  "error_code": "history_unavailable",
  "error_detail": "Requested pre-event history is not in the buffer."
}
```

See [Error code reference](#error-code-reference) for the full `error_code` enum and the
status codes each endpoint can return.

### Stream

| Field | Type | Description |
|---|---|---|
| `stream_id` | string | Identity given to the stream when it was attached. |
| `sensor_id` | string | Identity of the sensor; for a URI source, the name the caller chose. |
| `state` | string | One of `connecting`, `buffering`, `reconnecting`, `failed`. |
| `sync_confidence` | string | One of `ntp_synced`, `best_effort`, `unverified` — how far incoming timestamps can be trusted. |
| `buffer` | [`BufferStatus`](#bufferstatus) | Current buffer capacity and held range. |
| `stats.framerate` | number | Frames arriving per second, measured over the last second. |
| `stats.dropped_frames` | integer | Frames known lost or unusable since attachment. |
| `creation_ts` | string (date-time) | When the stream was attached. |

```json
{
  "stream_id": "str-1",
  "sensor_id": "cam-07",
  "state": "buffering",
  "sync_confidence": "best_effort",
  "buffer": {
    "capacity": 30,
    "held_bytes": 6000000,
    "oldest_ts": "2026-09-16T09:11:48.000000000Z",
    "newest_ts": "2026-09-16T09:12:00.000000000Z"
  },
  "stats": { "framerate": 30, "dropped_frames": 0 },
  "creation_ts": "2026-09-16T09:11:48.000000000Z"
}
```

#### BufferStatus

| Field | Type | Description |
|---|---|---|
| `capacity` | integer | Seconds of video the buffer is set up to hold, 5-300. |
| `held_bytes` | integer | Bytes the buffer is holding right now. |
| `oldest_ts` | string (date-time), nullable | Oldest time still held; `null` while empty. |
| `newest_ts` | string (date-time), nullable | Newest time still held; `null` while empty. |

### Recording

One record is one recording of one sensor.

| Field | Type | Description |
|---|---|---|
| `recording_id` | string | Recording identity. |
| `sensor_id` | string | Recorded sensor. |
| `stream_id` | string, nullable | The stream it was recorded from; `null` for an imported recording. |
| `state` | string | One of `recording`, `finalizing`, `ready`, `failed`. Media can only be retrieved once `ready`. |
| `start_ts` | string (date-time) | First moment covered, itself included. |
| `end_ts` | string (date-time), nullable | Moment coverage stops (exclusive); `null` while an open recording is still running. |
| `size_bytes` | integer, nullable | Size of the finished media; `null` until `ready`. |
| `metadata` | object | Whatever metadata the caller supplied, or `{}` if none was. |
| `creation_ts` | string (date-time) | Record creation time. |
| `expiry_ts` | string (date-time), nullable | When Stream Manager deletes the recording automatically. It is set when the recording becomes `ready` or `failed` and the deployment sets `RecordingRetention`. It is `null` when no retention is set; the recording then stays until you delete it. |
| `error_detail` | string, nullable | A short reason. It is present when `state` is `failed`. It is also present when `state` is `ready` and the storage quota stopped the recording early. |

```json
{
  "recording_id": "rec-2",
  "sensor_id": "cam-07",
  "stream_id": "str-1",
  "state": "ready",
  "start_ts": "2026-09-16T09:12:00.400000000Z",
  "end_ts": "2026-09-16T09:12:08.400000000Z",
  "size_bytes": 4194304,
  "metadata": { "incident_id": "incident-17" },
  "creation_ts": "2026-09-16T09:12:03.600000000Z",
  "expiry_ts": null,
  "error_detail": null
}
```

### MediaResult

Returned by the [Retrieval APIs](#retrieval-apis) when the reply is JSON rather than raw
media.

| Field | Type | Description |
|---|---|---|
| `recording_id` | string | The record the media was taken from. |
| `sensor_id` | string | The sensor the media belongs to. |
| `requested_start_ts` | string (date-time) | Time the caller asked for. |
| `requested_end_ts` | string (date-time), nullable | End the caller asked for (exclusive); `null` for a single frame. |
| `start_ts` | string (date-time) | Real time of the returned frame, or first frame of the clip. |
| `end_ts` | string (date-time), nullable | Where the clip really ends (exclusive); `null` for a single frame. |
| `url` | string | Origin-relative path that serves the file via [`GET /media/{recording-id}/{file}`](#get-produced-media) until `expiry_ts`. Never points at the original recording. |
| `expiry_ts` | string (date-time) | When `url` stops working; capped by the recording's own `expiry_ts`. |

### Deletion

Returned by `DELETE /streams/{stream-id}` and `DELETE /records/{recording-id}`.

| Field | Type | Description |
|---|---|---|
| `resource` | string | `stream` or `recording`. |
| `id` | string | Which resource was deleted. |
| `deleted` | boolean | Always `true`. For a recording, metadata deletion has finished; media cleanup can finish later. |

```json
{ "resource": "recording", "id": "rec-2", "deleted": true }
```

---

## Service APIs

### Service status

`GET /status`

Reports service status and the running build's version, build number, and build date.

```bash
curl -i http://localhost:8080/v1/status
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "ok",
  "version": "v0.1.0",
  "build_number": "42",
  "build_date": "2026-09-16T00:00:00+0000"
}
```

| Status | Meaning |
|---|---|
| 200 | Service status and build details. |

---

## Stream Attachment APIs

Attach sources, inspect buffers, resize buffers, and detach.

### Attach a source

`POST /streams`

Attaches an RTSP/RTSPS source and starts reading and buffering it. The reply returns before
any history has built up.

**Request body — `StreamCreate`**

| Field | Type | Required | Description |
|---|---|---|---|
| `sensor_id` | string | yes | Sensor identity; the name recordings will be filed under. One sensor can have many sources. |
| `source_uri` | string | yes | Absolute URI of the source, no credentials, up to 2048 characters. |
| `buffer_length` | integer | no | Seconds of history the buffer holds, 5-300. Default is 30. |

**Example — default buffer length**

```bash
curl -i -X POST http://localhost:8080/v1/streams \
  -H 'Content-Type: application/json' \
  -d '{
        "sensor_id": "cam-07",
        "source_uri": "rtsp://camera.example.com/live"
      }'
```

```http
HTTP/1.1 201 Created
Location: /v1/streams/str-1
Content-Type: application/json

{
  "stream_id": "str-1",
  "sensor_id": "cam-07",
  "state": "connecting",
  "sync_confidence": "unverified",
  "buffer": { "capacity": 30, "held_bytes": 0, "oldest_ts": null, "newest_ts": null },
  "stats": { "framerate": 0, "dropped_frames": 0 },
  "creation_ts": "2026-09-16T09:11:48.000000000Z"
}
```

**Example — explicit buffer length**

```bash
curl -i -X POST http://localhost:8080/v1/streams \
  -H 'Content-Type: application/json' \
  -d '{
        "sensor_id": "cam-08",
        "source_uri": "rtsp://192.168.1.50:554/stream1",
        "buffer_length": 120
      }'
```

**Error example — source already attached for the sensor**

```json
{
  "status": 409,
  "error_code": "stream_exists",
  "error_detail": "this source is already attached for the sensor as str-1"
}
```

| Status | `error_code` | Meaning |
|---|---|---|
| 201 | — | Stream attached. |
| 400 | `invalid_request` | Malformed body, missing fields, or `buffer_length` out of 5-300 range. |
| 409 | `stream_exists` | The same `source_uri` is already attached for that `sensor_id`; the existing `stream_id` is named in `error_detail`. |
| 415 | `unsupported_media` | The source is not RTSP/RTSPS H.264/H.265 video. Invalid URIs, embedded credentials, or a missing host return `400 invalid_request`. |
| 429 | `capacity_exhausted` | No room left for another stream. |

### List streams

`GET /streams`

Returns all attached streams in one page. Paging is not supported yet.

```bash
curl -i http://localhost:8080/v1/streams
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [
    {
      "stream_id": "str-1",
      "sensor_id": "cam-07",
      "state": "buffering",
      "sync_confidence": "best_effort",
      "buffer": {
        "capacity": 30,
        "held_bytes": 6000000,
        "oldest_ts": "2026-09-16T09:11:48.000000000Z",
        "newest_ts": "2026-09-16T09:12:00.000000000Z"
      },
      "stats": { "framerate": 30, "dropped_frames": 0 },
      "creation_ts": "2026-09-16T09:11:48.000000000Z"
    }
  ],
  "next_cursor": null
}
```

No matches returns `200` with an empty `items` list, never `404`.

| Status | Meaning |
|---|---|
| 200 | Page of `Stream` objects. |

### Get a stream

`GET /streams/{stream-id}`

Returns the complete stream, including its buffer and statistics.

```bash
curl -i http://localhost:8080/v1/streams/str-1
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "stream_id": "str-1",
  "sensor_id": "cam-07",
  "state": "buffering",
  "sync_confidence": "best_effort",
  "buffer": {
    "capacity": 30,
    "held_bytes": 6000000,
    "oldest_ts": "2026-09-16T09:11:48.000000000Z",
    "newest_ts": "2026-09-16T09:12:00.000000000Z"
  },
  "stats": { "framerate": 30, "dropped_frames": 0 },
  "creation_ts": "2026-09-16T09:11:48.000000000Z"
}
```

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | The `Stream` object. |
| 404 | `stream_not_found` | The stream is unknown or has been detached. |

### Detach a stream

`DELETE /streams/{stream-id}`

Stops reading the source and frees the buffer memory. Finished recordings stay retrievable.

```bash
curl -i -X DELETE http://localhost:8080/v1/streams/str-1
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{ "resource": "stream", "id": "str-1", "deleted": true }
```

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | Stream detached. |
| 404 | `stream_not_found` | Not attached. |
| 409 | `active_dependency` | A recording still holds a lease on the buffer. |

### Resize a stream buffer

`PUT /streams/{stream-id}/buffer`

Changes how many seconds of history the buffer holds. Growing keeps every existing
slice and lets the buffer accept more history; shrinking immediately discards the
oldest slices that no longer fit the smaller window. Requesting the current size
succeeds without changing anything. The same `buffer_length` limits as attachment
apply.

**Request body — `BufferUpdate`**

| Field | Type | Required | Description |
|---|---|---|---|
| `buffer_length` | integer | yes | New size in seconds, 5-300. |

```bash
curl -i -X PUT http://localhost:8080/v1/streams/str-1/buffer \
  -H 'Content-Type: application/json' \
  -d '{ "buffer_length": 60 }'
```

```json
{
  "stream_id": "str-1",
  "sensor_id": "cam-07",
  "state": "buffering",
  "sync_confidence": "ntp_synced",
  "buffer": { "capacity": 60, "held_bytes": 1048576, "oldest_ts": "2026-09-16T09:11:18.000000000Z", "newest_ts": "2026-09-16T09:11:48.000000000Z" },
  "stats": { "framerate": 25, "dropped_frames": 0 },
  "creation_ts": "2026-09-16T09:10:00.000000000Z"
}
```

**Error example — out of range**

```json
{
  "status": 400,
  "error_code": "invalid_request",
  "error_detail": "buffer_length must be between 5 and 300 seconds"
}
```

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | Buffer resized; the full stream, including the new `buffer.capacity`. |
| 400 | `invalid_request` | Missing `buffer_length`, or it is out of the 5-300 range. |
| 404 | `stream_not_found` | Unknown stream. |

---

## Recording Storage APIs

Start, stop, find, read, and delete recordings.

### Start a recording

`POST /records/start`

Saves the video around an event from one attached stream. If the stream lacks the
requested history, no record is created. Video is copied as whole keyframe-aligned
MPEG-TS slices without re-encoding; the stored window can extend to the enclosing
keyframes, and `ready` records report those actual bounds.
Stream Manager preserves the input time base when it copies video with FFmpeg.
This prevents timestamp rounding during the copy.

**Request body — `RecordStart`**

| Field | Type | Required | Description |
|---|---|---|---|
| `stream_id` | string | yes | The attached stream to record. |
| `start_ts` | string (date-time) | yes | The moment the event happened (T), on the source clock. Cannot be later than the newest video frame from the source. |
| `duration` | number | no | Positive seconds to record after T. Omit for an open recording ended later with `/records/stop`. |
| `pre_event_duration` | number | no | Seconds of history before T to keep, 0-300, default 0. Must already be in the buffer. |
| `metadata` | object | no | Arbitrary metadata to store with the record. |

**Example — fixed-length recording with pre-event history and metadata**

```bash
curl -i -X POST http://localhost:8080/v1/records/start \
  -H 'Content-Type: application/json' \
  -d '{
        "stream_id": "str-1",
        "start_ts": "2026-09-16T09:12:03.400000000Z",
        "duration": 5,
        "pre_event_duration": 3,
        "metadata": { "incident_id": "incident-17" }
      }'
```

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "recordings": [
    {
      "recording_id": "rec-2",
      "sensor_id": "cam-07",
      "stream_id": "str-1",
      "state": "recording",
      "start_ts": "2026-09-16T09:12:00.400000000Z",
      "end_ts": "2026-09-16T09:12:08.400000000Z",
      "size_bytes": null,
      "metadata": { "incident_id": "incident-17" },
      "creation_ts": "2026-09-16T09:12:03.600000000Z",
      "expiry_ts": null,
      "error_detail": null
    }
  ]
}
```

**Example — open-ended recording (no `duration`, no `pre_event_duration`, no `metadata`)**

Omitting `duration` starts a recording that keeps running until `/records/stop` is
called; omitting `pre_event_duration` defaults it to 0; omitting `metadata` stores `{}`.

```bash
curl -i -X POST http://localhost:8080/v1/records/start \
  -H 'Content-Type: application/json' \
  -d '{
        "stream_id": "str-1",
        "start_ts": "2026-09-16T09:12:03.400000000Z"
      }'
```

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "recordings": [
    {
      "recording_id": "rec-open-1",
      "sensor_id": "cam-07",
      "stream_id": "str-1",
      "state": "recording",
      "start_ts": "2026-09-16T09:12:03.400000000Z",
      "end_ts": null,
      "size_bytes": null,
      "metadata": {},
      "creation_ts": "2026-09-16T09:12:03.600000000Z",
      "expiry_ts": null,
      "error_detail": null
    }
  ]
}
```

**Error example — requested history not in the buffer**

```json
{
  "status": 409,
  "error_code": "history_unavailable",
  "error_detail": "requested history is not available"
}
```

| Status | `error_code` | Meaning |
|---|---|---|
| 201 | — | Record accepted in the `recording` state. Acceptance does not mean the media is finished. |
| 400 | `invalid_request` / `invalid_selector` / `invalid_timestamp` | Malformed body or missing `start_ts` (`invalid_request`); malformed `stream_id` (`invalid_selector`); invalid `start_ts`, or `start_ts` later than the newest video frame (`invalid_timestamp`); invalid `duration` or `pre_event_duration` (`invalid_request`). |
| 404 | `stream_not_found` | Unknown stream. |
| 409 | `history_unavailable` | Requested history unavailable, or the stream is not buffering with NTP-synced timestamps. |
| 429 | `capacity_exhausted` | Recording capacity reached. |
| 507 | `storage_full` | The recording storage quota is reached. Delete recordings to free space. |

### Stop an open recording

`POST /records/stop`

Stops an open recording. The stop time is the time of the newest video frame from
the source, on the source clock. The host clock is not used. The stop time is fixed
and does not move if the request is repeated. An already finished recording returns `200` with the current record.

**Request body — `RecordStop`**

| Field | Type | Required | Description |
|---|---|---|---|
| `recording_id` | string | yes | The open recording to stop. |

```bash
curl -i -X POST http://localhost:8080/v1/records/stop \
  -H 'Content-Type: application/json' \
  -d '{ "recording_id": "rec-open-1" }'
```

**Still finalizing — `202 Accepted`**

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "recording_id": "rec-open-1",
  "sensor_id": "cam-07",
  "stream_id": "str-1",
  "state": "finalizing",
  "start_ts": "2026-09-16T09:12:03.400000000Z",
  "end_ts": "2026-09-16T09:15:10.000000000Z",
  "size_bytes": null,
  "metadata": {},
  "creation_ts": "2026-09-16T09:12:03.600000000Z",
  "expiry_ts": null,
  "error_detail": null
}
```

**Already finished — `200 OK`**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "recording_id": "rec-open-1",
  "sensor_id": "cam-07",
  "stream_id": "str-1",
  "state": "ready",
  "start_ts": "2026-09-16T09:12:03.400000000Z",
  "end_ts": "2026-09-16T09:15:10.000000000Z",
  "size_bytes": 20971520,
  "metadata": {},
  "creation_ts": "2026-09-16T09:12:03.600000000Z",
  "expiry_ts": null,
  "error_detail": null
}
```

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | The recording was already finished; the current record is returned. |
| 202 | — | Record accepted for finalizing. |
| 400 | `invalid_request` | Malformed body or invalid `recording_id`. |
| 404 | `recording_not_found` | Unknown recording. |
| 409 | `record_not_ready` | The record is not an active open recording. Repeated stops while finalizing retain the original stop target and return `202`. |
| 409 | `history_unavailable` | The source sent no video frame after the recording start. |

### Find records

`GET /records`

Returns a page of records. All query parameters are optional and AND-combined. A match
requires only that the recorded window overlaps the filter.

| Parameter | In | Type | Description |
|---|---|---|---|
| `sensor_id` | query | string | Only records from this sensor, imported as well as live. |
| `stream_id` | query | string | Only records from this stream (never includes imports). |
| `start_ts` | query | date-time | Inclusive lower bound of the filter window. |
| `end_ts` | query | date-time | Exclusive upper bound of the filter window; must be later than `start_ts` when both are supplied. |
| `expiry_ts` | query | date-time | Keep only records expiring at or before this time. |
| `state` | query | string | One of `recording`, `finalizing`, `ready`, `failed`. |
| `metadata[key]` | query | string | One or more metadata keys/values to match against. Repeatable. |
| `cursor` | query | string | Opaque cursor from a previous page's `next_cursor`. |
| `limit` | query | integer | Items per page, 1-100, default 20. |

**Example — filter by sensor and state, default page size**

```bash
curl -i "http://localhost:8080/v1/records?sensor_id=cam-07&state=ready"
```

**Example — filter by time window and metadata, custom page size**

```bash
curl -i "http://localhost:8080/v1/records?start_ts=2026-09-16T09:00:00Z&end_ts=2026-09-16T10:00:00Z&metadata%5Bincident_id%5D=incident-17&limit=10"
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "items": [
    {
      "recording_id": "rec-2",
      "sensor_id": "cam-07",
      "stream_id": "str-1",
      "state": "ready",
      "start_ts": "2026-09-16T09:12:00.400000000Z",
      "end_ts": "2026-09-16T09:12:08.400000000Z",
      "size_bytes": 4194304,
      "metadata": { "incident_id": "incident-17" },
      "creation_ts": "2026-09-16T09:12:03.600000000Z",
      "expiry_ts": null,
      "error_detail": null
    }
  ],
  "next_cursor": null
}
```

**Example — paging with a cursor**

```bash
curl -i "http://localhost:8080/v1/records?limit=20&cursor=MTc4OTU0OTkyMzYwMDAwMDAwMApBQUVDQXdRRkJnY0lDUW9MREEwT0R3"
```

No matches returns `200` with an empty `items` list, never `404`.

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | Page of `Recording` objects. |
| 400 | `invalid_request` / `invalid_timestamp` | Invalid ID, state, metadata filter, cursor, or limit (`invalid_request`); invalid timestamp filter (`invalid_timestamp`). Stream Manager reports all invalid ID, state, `limit`, and timestamp parameters together in `error_detail`, one per line. The code is `invalid_timestamp` only when all of them are timestamp errors. |

### Get a record

`GET /records/{recording-id}`

Returns the complete record, available in every state. A `failed` record carries
`error_detail`.

```bash
curl -i http://localhost:8080/v1/records/rec-2
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "recording_id": "rec-2",
  "sensor_id": "cam-07",
  "stream_id": "str-1",
  "state": "ready",
  "start_ts": "2026-09-16T09:12:00.400000000Z",
  "end_ts": "2026-09-16T09:12:08.400000000Z",
  "size_bytes": 4194304,
  "metadata": { "incident_id": "incident-17" },
  "creation_ts": "2026-09-16T09:12:03.600000000Z",
  "expiry_ts": null,
  "error_detail": null
}
```

**Example — a failed record**

```json
{
  "recording_id": "rec-9",
  "sensor_id": "cam-07",
  "stream_id": "str-1",
  "state": "failed",
  "start_ts": "2026-09-16T09:12:00.000000000Z",
  "end_ts": null,
  "size_bytes": null,
  "metadata": {},
  "creation_ts": "2026-09-16T09:12:03.600000000Z",
  "expiry_ts": null,
  "error_detail": "recording interrupted by service restart"
}
```

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | The `Recording` object. |
| 404 | `recording_not_found` | Unknown or deleted recording. |

### Delete a record

`DELETE /records/{recording-id}`

Deletes the record's metadata first, then attempts to delete its media. If metadata
deletion fails, the request returns `503` and the media stays unchanged.
If media deletion fails or an extraction still uses the media, the request returns
`200`. Stream Manager logs the deferred deletion. The cleanup job retries removal of
media without metadata at startup and every 24 hours. The media continues to count
toward the storage quota until it is removed.
Deleting again, or reading the deleted recording, returns `404`.

```bash
curl -i -X DELETE http://localhost:8080/v1/records/rec-2
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{ "resource": "recording", "id": "rec-2", "deleted": true }
```

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | Record deleted. |
| 404 | `recording_not_found` | Unknown or already deleted recording. |
| 409 | `record_not_ready` | Record is still recording or finalizing. |
| 503 | `storage_unavailable` | Metadata deletion failed. The record and media remain; retry later. |

---

## Retrieval APIs

Extracts media from a `ready` record. Use the `Accept` header to select the response.
There are no separate `/url` endpoints.

| `Accept` | Response |
|---|---|
| Missing, `*/*`, or `application/json` | JSON `MediaResult` with a temporary download link. |
| `image/jpeg` or `image/png` on `/frame` | Image bytes in the selected format. |
| `video/mp4` on `/clip` | MP4 bytes. |
| No acceptable supported type | `406 not_acceptable`. |

The service respects quality values (`q`) and excludes types with `q=0`.
For equal quality values, the service prefers JSON, then JPEG, then PNG.
Responses include `Vary: Accept`. Errors use JSON, including errors for binary requests.
The `/media` endpoint serves the file referenced by a JSON response.

### Extract a frame

`GET /retrieve/{recording-id}/frame`

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `recording-id` | path | string | yes | The recording, e.g. `rec-2`. |
| `timestamp` | query | date-time | yes | Time wanted; must fall inside `[start_ts, end_ts)`. |
| `format` | query | string | no | Optional image format: `jpeg` or `png`. JSON links default to JPEG. For binary responses, `Accept` selects the format when this parameter is absent. A conflict with an explicit format returns `406`. |
| `match` | query | string | no | `nearest` (default, ties go to the earlier frame) or `exact` (404 if nothing sits exactly on that time). |

**JSON reply (default `Accept: application/json`)**

```bash
curl -i "http://localhost:8080/v1/retrieve/rec-2/frame?timestamp=2026-09-16T09:12:03.400000000Z"
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Frame-Timestamp: 2026-09-16T09:12:03.400000000Z
X-Exact-Match: true
Cache-Control: no-store

{
  "recording_id": "rec-2",
  "sensor_id": "cam-07",
  "requested_start_ts": "2026-09-16T09:12:03.400000000Z",
  "requested_end_ts": null,
  "start_ts": "2026-09-16T09:12:03.400000000Z",
  "end_ts": null,
  "url": "/v1/media/rec-2/frame-3000000000.jpg",
  "expiry_ts": "2026-09-16T09:20:00.000000000Z"
}
```

**Raw bytes reply with a `png` format and nearest match**

```bash
curl -i "http://localhost:8080/v1/retrieve/rec-2/frame?timestamp=2026-09-16T09:12:03.700000000Z&format=png&match=nearest" \
  -H 'Accept: image/png' \
  -o frame.png
```

```http
HTTP/1.1 200 OK
Content-Type: image/png
X-Frame-Timestamp: 2026-09-16T09:12:03.666666667Z
X-Exact-Match: false
```

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | `MediaResult`, or the image bytes when an image `Accept` header is used. |
| 400 | `invalid_timestamp` | Missing or invalid `timestamp`. |
| 400 | `invalid_request` | Unsupported `format` or `match`. |
| 404 | `recording_not_found` / `frame_not_found` | Recording not found, timestamp outside coverage, exact frame missing, or no decodable frame available for the requested time. |
| 406 | `not_acceptable` | Incompatible `Accept` header. |
| 409 | `record_not_ready` | Record not ready. |
| 429 | `capacity_exhausted` | Extraction capacity reached. |
| 507 | `storage_full` | The recording storage quota is reached. Delete recordings to free space. |
| 503 | `storage_unavailable` | Extraction or storage failure. |

### Extract a clip

`GET /retrieve/{recording-id}/clip`

The whole requested span must be covered by the recording; a gap returns `404`.

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `recording-id` | path | string | yes | The recording, e.g. `rec-2`. |
| `start_ts` | query | date-time | yes | Where the clip starts, inclusive. Must be RFC 3339 UTC and end in `Z`. |
| `duration` | query | number | yes | Positive clip length in seconds. The full interval must be covered by the recording. |
| `format` | query | string | no | `mp4` (default) |

```bash
curl -i "http://localhost:8080/v1/retrieve/rec-2/clip?start_ts=2026-09-16T09:12:00.400000000Z&duration=5"
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Frame-Timestamp: 2026-09-16T09:12:00.400000000Z
X-Exact-Match: true
Cache-Control: no-store

{
  "recording_id": "rec-2",
  "sensor_id": "cam-07",
  "requested_start_ts": "2026-09-16T09:12:00.400000000Z",
  "requested_end_ts": "2026-09-16T09:12:05.400000000Z",
  "start_ts": "2026-09-16T09:12:00.400000000Z",
  "end_ts": "2026-09-16T09:12:05.400000000Z",
  "url": "/v1/media/rec-2/clip-0-5000000000.mp4",
  "expiry_ts": "2026-09-16T09:20:00.000000000Z"
}
```

**Raw clip bytes in `mp4` format**

```bash
curl -i "http://localhost:8080/v1/retrieve/rec-2/clip?start_ts=2026-09-16T09:12:00.400000000Z&duration=8&format=mp4" \
  -H 'Accept: video/mp4' \
  -o clip.mp4
```

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | `MediaResult`, or video bytes when a video `Accept` header is used. |
| 400 | `invalid_timestamp` | Missing or invalid `start_ts`. |
| 400 | `invalid_request` | Missing or invalid `duration`, or unsupported `format`. |
| 404 | `recording_not_found` / `clip_not_found` | Recording not found, the requested interval is not fully covered, or no clip available for the requested interval. |
| 406 | `not_acceptable` | Incompatible `Accept` header. |
| 409 | `record_not_ready` | Record not ready. |
| 429 | `capacity_exhausted` | Extraction capacity reached. |
| 507 | `storage_full` | The recording storage quota is reached. Delete recordings to free space. |
| 503 | `storage_unavailable` | Extraction or storage failure. |

### Get produced media

`GET /media/{recording-id}/{file}`

Serves the bytes of a frame or clip named by a `MediaResult`'s `url`. When
`DerivedMediaTTL` is greater than `0`, the file is available for that many minutes
after it is cut, capped by the recording's own `expiry_ts`. Set `DerivedMediaTTL` to
`-1` to disable this TTL. In that case, the file stays available until its recording
expires or is deleted. `expiry_ts` is `null` when neither expiry applies. See
[Configuration](../configuration.md#frame-and-clip-lifetime).

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `recording-id` | path | string | yes | The recording, e.g. `rec-2`. |
| `file` | path | string | yes | The file name from a `MediaResult`'s `url`, e.g. `frame-3000000000.jpg` or `clip-0-5000000000.mp4`. |

```bash
curl -i "http://localhost:8080/v1/media/rec-2/frame-3000000000.jpg" -o frame.jpg
```

```http
HTTP/1.1 200 OK
Content-Type: image/jpeg
Cache-Control: private, max-age=712
Expires: Wed, 16 Sep 2026 09:20:00 GMT
X-Content-Type-Options: nosniff
```

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | The frame or clip bytes (`image/jpeg`, `image/png`, or `video/mp4`). |
| 404 | `recording_not_found` / `frame_not_found` / `clip_not_found` | Unknown recording, or the frame or clip is missing or past its `expiry_ts`. |

---

## Error code reference

| `error_code` | Typical status | Meaning |
|---|---|---|
| `invalid_request` | 400 | The request is malformed, or its fields contradict each other. |
| `invalid_selector` | 400 | `stream_id` in `POST /records/start` is missing or malformed. |
| `invalid_timestamp` | 400 | A timestamp is malformed or out of range. A `start_ts` in `POST /records/start` that is later than the newest video frame from the source also uses this code. A missing `start_ts` there returns `invalid_request`. |
| `stream_not_found` | 404 | The stream is unknown or has been detached. |
| `recording_not_found` | 404 | The recording is unknown or has been deleted. |
| `frame_not_found` | 404 | The requested frame is not covered, no frame sits at the exact requested time (`match=exact`), no decodable frame is available for the requested time, or a frame file is missing or expired. |
| `clip_not_found` | 404 | The requested clip interval is not covered, no clip is available for the requested interval, or a clip file is missing or expired. |
| `not_acceptable` | 406 | The `Accept` header cannot be satisfied. |
| `stream_exists` | 409 | The same `source_uri` is already attached for that `sensor_id`; the existing `stream_id` is named in `error_detail`. |
| `record_not_ready` | 409 | The record is not in a state that allows the requested action. |
| `history_unavailable` | 409 | Requested history is unavailable, or the stream is not buffering with NTP-synced timestamps. |
| `active_dependency` | 409 | Another resource still depends on this one (e.g. an active recording). |
| `unsupported_media` | 415 | The source is not RTSP/RTSPS H.264/H.265 video. |
| `capacity_exhausted` | 429 | Capacity limit reached for a stream, recording, or extraction. |
| `internal_error` | 500 | An unexpected server-side failure. |
| `storage_full` | 507 | The recording storage quota (`RecordingStorageSize`) is reached. |
| `storage_unavailable` | 503 | Storage or media processing failed. |
