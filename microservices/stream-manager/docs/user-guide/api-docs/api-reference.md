# API Reference

This reference documents every endpoint published in [`openapi.yaml`](./openapi.yaml), with
sample requests, `curl` commands, and sample responses drawn from the current implementation.
It complements the OpenAPI spec; when the two disagree, `openapi.yaml` is authoritative.

> [!NOTE]
> This API is a **working draft** and may still change.

> [!IMPORTANT]
> The service configuration can be overridden using a `config.json` file placed in the application root.
> A sample `config.json.sample` file will be provided at the application root for reference.


## Base URL and versioning

All endpoints are mounted under the `/v1` prefix. The service listens on `8080` port by default
(override this using the `config.json`). Examples in this document use:

```
http://localhost:8080/v1
```

## Conventions

- **Content type**: requests and responses use `application/json`, except the media
  endpoints (`/replays/*`), which may return raw image/video bytes (see
  [Replay APIs](#replay-apis-planned)).
- **Timestamps**: RFC 3339, UTC, with a `Z` suffix and up to 9 fractional digits
  (nanosecond precision), for example `2026-09-16T09:12:03.400000000Z`.
- **Identifiers**: `stream_id`, `recording_id`, and `sensor_id` are opaque strings, 1-128
  characters, matching `^[A-Za-z0-9][A-Za-z0-9._:-]*$`.
- **Pagination**: list endpoints accept `cursor` and `limit` (1-100, default 20) query
  parameters and return `next_cursor`, an opaque token to pass back as `cursor` for the next
  page. `next_cursor` is `null` when there are no more pages. Stream listing is not paged yet
  (`next_cursor` is always `null`).
- **Metadata filtering**: `GET /records` accepts repeated `metadata[key]=value` query
  parameters, AND-combined with every other filter.
- **Authentication**: the spec documents `401`/`403` responses for future use; no
  authentication is enforced by the current build.
- **Errors**: every non-2xx response returns the same [`Error`](#error) shape.

## Common response objects

> [!CAUTION]
> The format of different IDs being used in this reference file could be different from the actual IDs used in the implementation.
> Dummy IDs (like `str-1`, `cam-07`, `rec-3`) are used in this reference as the IDs form factor is still subject to change.

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

One record is one recording of one sensor, matching exactly one row of the records table.

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
| `expiry_ts` | string (date-time), nullable | When the recording is due to be deleted; `null` when the deployment default applies. |
| `error_detail` | string, nullable | A short reason, present only when `state` is `failed`. |

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

Returned by the [Replay APIs](#replay-apis-planned) when the reply is JSON rather than raw
media.

| Field | Type | Description |
|---|---|---|
| `recording_id` | string | The record the media was taken from. |
| `sensor_id` | string | The sensor the media belongs to. |
| `media_type` | string | `frame` or `clip`. |
| `content_type` | string | File type produced, e.g. `image/jpeg` or `video/mp4`. |
| `requested_start_ts` | string (date-time) | Time the caller asked for. |
| `requested_end_ts` | string (date-time), nullable | End the caller asked for (exclusive); `null` for a single frame. |
| `start_ts` | string (date-time) | Real time of the returned frame, or first frame of the clip. |
| `end_ts` | string (date-time), nullable | Where the clip really ends (exclusive); `null` for a single frame. |
| `url` | string | Short-lived link to the produced file. Never points at the original recording. |
| `expiry_ts` | string (date-time) | Expiry of `url`, same as the recording's lifetime. |

### Deletion

Returned by `DELETE /streams/{stream-id}` and `DELETE /records/{recording-id}`.

| Field | Type | Description |
|---|---|---|
| `resource` | string | `stream` or `recording`. |
| `id` | string | Which resource was deleted. |
| `deleted` | boolean | Always `true`, sent only once the deletion has finished. |

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
  "build_date": "2026-09-16T00:00:00.000000000Z"
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
| `sensor_id` | string | yes | Sensor identity; the name recordings will be filed under. |
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

**Error example — sensor already attached**

```json
{
  "status": 409,
  "error_code": "stream_exists",
  "error_detail": "stream on provided source_uri on sensor cam-07 is already attached as str-1"
}
```

| Status | `error_code` | Meaning |
|---|---|---|
| 201 | — | Stream attached. |
| 400 | `invalid_request` | Malformed body, missing fields, or `buffer_length` out of 5-300 range. |
| 401 | `unauthenticated` | Reserved for future auth. |
| 403 | `forbidden` | Reserved for future auth. |
| 404 | — | Unknown sensor. |
| 409 | `stream_exists` | That sensor is already attached; the existing `stream_id` is named in `error_detail`. |
| 415 | `unsupported_media` | Unsupported protocol or codec. |
| 429 | `capacity_exhausted` | No room left for another stream. |
| 503 | — | Sensor Manager could not be reached. |

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
| 401 / 403 | Reserved for future auth. |

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
| 401 / 403 | | Reserved for future auth. |
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
| 401 / 403 | | Reserved for future auth. |
| 404 | `stream_not_found` | Not attached. |
| 409 | `active_dependency` | A recording is still using the stream. |
| 503 | | The buffer could not be released safely. |

### Resize a stream buffer

`PUT /streams/{stream-id}/buffer`

> [!NOTE]
> **Not implemented yet.** This endpoint always returns `501 not_implemented` in the
> current build. Set the buffer size with `buffer_length` when attaching the stream; it
> cannot be changed afterwards yet.

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
  "status": 501,
  "error_code": "not_implemented",
  "error_detail": "resizing a stream buffer is not implemented yet"
}
```

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | Buffer status (planned). |
| 400 | | Invalid value (planned). |
| 401 / 403 | | Reserved for future auth. |
| 404 | `stream_not_found` | Unknown stream (planned). |
| 409 | | A running recording still needs the data that would be freed (planned). |
| 429 | `capacity_exhausted` | Not enough memory left to grow the buffer (planned). |
| 501 | `not_implemented` | Resizing is not implemented yet — returned today for every call. |

---

## Recording Storage APIs

Start, stop, find, read, and delete recordings.

### Start a recording

`POST /records/start`

Saves the video around an event from one attached stream. If the stream lacks the
requested history, no record is created. Video is copied as whole keyframe-aligned
MPEG-TS slices without re-encoding; the stored window can extend to the enclosing
keyframes, and `ready` records report those actual bounds.

**Request body — `RecordStart`**

| Field | Type | Required | Description |
|---|---|---|---|
| `stream_id` | string | yes | The attached stream to record. |
| `start_ts` | string (date-time) | yes | The moment the event happened (T). Cannot be in the future. |
| `duration` | number | no | Seconds to record after T. Omit for an open recording ended later with `/records/stop`. |
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
| 400 | `invalid_request` / `invalid_selector` / `invalid_timestamp` | Invalid `stream_id`, missing/invalid `start_ts`, or `duration`/`pre_event_duration` out of range. |
| 401 / 403 | | Reserved for future auth. |
| 404 | `stream_not_found` | Unknown stream. |
| 409 | `history_unavailable` | Requested history unavailable, or the stream is not buffering with NTP-synced timestamps. |
| 429 | `capacity_exhausted` | Recording capacity reached. |

### Stop an open recording

`POST /records/stop`

Stops an open recording. The stop time is fixed and does not move if the request is
repeated. An already finished recording returns `200` with the current record.

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
| 401 / 403 | | Reserved for future auth. |
| 404 | `record_not_found` | Unknown record. |
| 409 | `record_not_ready` | The record is not an active open recording. Repeated stops while finalizing retain the original stop target and return `202`. |

### Find records

`GET /records`

Returns a page of records. All query parameters are optional and AND-combined. A match
requires only that the recorded window overlaps the filter.

| Parameter | In | Type | Description |
|---|---|---|---|
| `sensor_id` | query | string | Only records from this sensor, imported as well as live. |
| `stream_id` | query | string | Only records from this stream (never includes imports). |
| `start_ts` | query | date-time | Near end of the overlap window `[start_ts, end_ts)`. |
| `end_ts` | query | date-time | Far end of that window; must be later than `start_ts` when both are supplied. |
| `expiry_ts` | query | date-time | Keep only records expiring before this time. |
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
curl -i "http://localhost:8080/v1/records?start_ts=2026-09-16T09:00:00Z&end_ts=2026-09-16T10:00:00Z&metadata[incident_id]=incident-17&limit=10"
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
curl -i "http://localhost:8080/v1/records?limit=20&cursor=MTc1ODAwMDAwMDAwMDAwMDAwMA..cmVjLTE"
```

No matches returns `200` with an empty `items` list, never `404`.

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | Page of `Recording` objects. |
| 400 | — | Invalid filter, cursor, or limit. |
| 401 / 403 | | Reserved for future auth. |

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
| 401 / 403 | | Reserved for future auth. |
| 404 | `record_not_found` | Unknown or deleted record. |

### Delete a record

`DELETE /records/{recording-id}`

Deletes the record and its media. The reply comes only once both the media and its row
are gone. Deleting again, or reading it afterwards, returns `404`.

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
| 401 / 403 | | Reserved for future auth. |
| 404 | `record_not_found` | Unknown or already deleted record. |
| 409 | `active_dependency` | Record is still recording or finalizing. |
| 503 | `storage_unavailable` | Storage cleanup failed, leaving the record for retry. |

---

## Replay APIs

> [!NOTE]
> The Replay APIs are **documented but not yet wired up** in this build — there are no
> live routes for `/replays/*` today. They are kept in the spec as the planned contract.
> The APIs will be added in next updates.

Extracts frames and clips from a `ready` record, or hands back a short-lived link to the
produced file, depending on the `Accept` header.

### Extract a frame

`GET /replays/{recording-id}/frame`

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `recording-id` | path | string | yes | The recording, e.g. `rec-2`. |
| `timestamp` | query | date-time | yes | Time wanted; must fall inside `[start_ts, end_ts)`. |
| `format` | query | string | no | `jpeg` (default) or `png`. |
| `match` | query | string | no | `nearest` (default, ties go to the earlier frame) or `exact` (404 if nothing sits exactly on that time). |

**JSON reply (default `Accept: application/json`)**

```bash
curl -i "http://localhost:8080/v1/replays/rec-2/frame?timestamp=2026-09-16T09:12:03.400000000Z"
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
  "media_type": "frame",
  "content_type": "image/jpeg",
  "requested_start_ts": "2026-09-16T09:12:03.400000000Z",
  "requested_end_ts": null,
  "start_ts": "2026-09-16T09:12:03.400000000Z",
  "end_ts": null,
  "url": "https://sm.example.com/v1/media/eyJ0eXAi...",
  "expiry_ts": "2026-09-16T09:20:00.000000000Z"
}
```

**Raw bytes reply with a `png` format and nearest match**

```bash
curl -i "http://localhost:8080/v1/replays/rec-2/frame?timestamp=2026-09-16T09:12:03.700000000Z&format=png&match=nearest" \
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
| 400 | `invalid_timestamp` | Invalid timestamp, format, or match. |
| 401 / 403 | | Reserved for future auth. |
| 404 | `record_not_found` / `frame_not_found` | Record not found, timestamp outside coverage, or exact frame missing. |
| 406 | `not_acceptable` | Incompatible `Accept` header. |
| 409 | `record_not_ready` | Record not ready. |
| 415 | `unsupported_media` | Undecodable profile. |
| 429 | `capacity_exhausted` | Extraction capacity reached. |
| 503 | `storage_unavailable` | Extraction or storage failure. |

### Get an HTTP link to a frame

`GET /replays/{recording-id}/frame/url`

Same parameters as [Extract a frame](#extract-a-frame), but always returns a
`MediaResult` link regardless of `Accept`.

```bash
curl -i "http://localhost:8080/v1/replays/rec-2/frame/url?timestamp=2026-09-16T09:12:03.400000000Z&format=jpeg&match=exact"
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "recording_id": "rec-2",
  "sensor_id": "cam-07",
  "media_type": "frame",
  "content_type": "image/jpeg",
  "requested_start_ts": "2026-09-16T09:12:03.400000000Z",
  "requested_end_ts": null,
  "start_ts": "2026-09-16T09:12:03.400000000Z",
  "end_ts": null,
  "url": "https://sm.example.com/v1/media/eyJ0eXAi...",
  "expiry_ts": "2026-09-16T09:20:00.000000000Z"
}
```

Status codes and `error_code`s are identical to [Extract a frame](#extract-a-frame).

### Extract a clip

`GET /replays/{recording-id}/clip`

The whole requested span must be covered by the recording; a gap returns `404`.

| Parameter | In | Type | Required | Description |
|---|---|---|---|---|
| `recording-id` | path | string | yes | The recording, e.g. `rec-2`. |
| `start_ts` | query | date-time | yes | Where the clip starts, inclusive. |
| `duration` | query | number | yes | Clip length in seconds, within the configured limit. |
| `format` | query | string | no | `mp4` (default) |

```bash
curl -i "http://localhost:8080/v1/replays/rec-2/clip?start_ts=2026-09-16T09:12:00.400000000Z&duration=5"
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Frame-Timestamp: 2026-09-16T09:12:00.400000000Z
X-Exact-Match: true

{
  "recording_id": "rec-2",
  "sensor_id": "cam-07",
  "media_type": "clip",
  "content_type": "video/mp4",
  "requested_start_ts": "2026-09-16T09:12:00.400000000Z",
  "requested_end_ts": "2026-09-16T09:12:05.400000000Z",
  "start_ts": "2026-09-16T09:12:00.400000000Z",
  "end_ts": "2026-09-16T09:12:05.400000000Z",
  "url": "https://sm.example.com/v1/media/eyJ0eXAi...",
  "expiry_ts": "2026-09-16T09:20:00.000000000Z"
}
```

**Raw clip bytes in `mp4` format**

```bash
curl -i "http://localhost:8080/v1/replays/rec-2/clip?start_ts=2026-09-16T09:12:00.400000000Z&duration=8&format=mp4" \
  -H 'Accept: video/mp4' \
  -o clip.mp4
```

| Status | `error_code` | Meaning |
|---|---|---|
| 200 | — | `MediaResult`, or video bytes when a video `Accept` header is used. |
| 400 | `invalid_request` | Invalid range or both end selectors. |
| 401 / 403 | | Reserved for future auth. |
| 404 | `record_not_found` | Interval not covered. |
| 406 | `not_acceptable` | Incompatible `Accept` header. |
| 409 | `record_not_ready` | Record not ready. |
| 415 | `unsupported_media` | Unavailable output profile. |
| 429 | `capacity_exhausted` | Extraction capacity reached. |
| 503 | `storage_unavailable` | Extraction or storage failure. |

### Get an HTTP link to a clip

`GET /replays/{recording-id}/clip/url`

Same parameters as [Extract a clip](#extract-a-clip), but always returns a `MediaResult`
link regardless of `Accept`.

```bash
curl -i "http://localhost:8080/v1/replays/rec-2/clip/url?start_ts=2026-09-16T09:12:00.400000000Z&duration=5&format=mp4"
```

Status codes and `error_code`s are identical to [Extract a clip](#extract-a-clip).

---


---

## Error code reference

| `error_code` | Typical status | Meaning |
|---|---|---|
| `invalid_request` | 400 | The request is malformed, or its fields contradict each other. |
| `invalid_selector` | 400 | A referenced identifier (e.g. `stream_id`) is malformed. |
| `invalid_timestamp` | 400 | A timestamp is missing, malformed, or out of the allowed range. |
| `unauthenticated` | 401 | No credentials were supplied, or the access token is not valid. |
| `forbidden` | 403 | The caller is not allowed. |
| `stream_not_found` | 404 | The stream is unknown or has been detached. |
| `record_not_found` | 404 | The record is unknown or has been deleted. |
| `frame_not_found` | 404 | No frame sits at the exact requested time (`match=exact`). |
| `not_acceptable` | 406 | The `Accept` header cannot be satisfied. |
| `stream_exists` | 409 | The sensor is already attached; the existing `stream_id` is named in `error_detail`. |
| `record_not_ready` | 409 | The record is not in a state that allows the requested action. |
| `history_unavailable` | 409 | Requested pre-event or playback history is not in the buffer. |
| `active_dependency` | 409 | Another resource still depends on this one (e.g. an active recording). |
| `payload_too_large` | 413 | The upload is bigger or longer than the configured limit. |
| `unsupported_media` | 415 | Unsupported protocol, codec, or output profile. |
| `capacity_exhausted` | 429 | No room left for another stream, more memory, or another extraction. |
| `internal_error` | 500 | An unexpected server-side failure. |
| `storage_unavailable` | 503 | Storage or an upstream dependency could not be reached. |
| `not_implemented` | 501 | The endpoint exists in the spec but is not implemented yet. |
