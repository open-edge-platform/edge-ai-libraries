# API Reference

The API uses the `/v1` path prefix. The default base URL is `http://localhost:18080`.
Request and response bodies use JSON unless a route returns media bytes.

For a working RTSP example, see [Get Started](get-started.md).

## Common rules

- Timestamps use RFC 3339. Stream and recording lifecycle timestamps must be UTC and end in `Z`.
- JSON request bodies must contain one object. Unknown fields are rejected.
- Errors use this shape:

```json
{
  "status": 400,
  "error_code": "invalid_request",
  "error_details": "request details"
}
```

## Service

| Method and path | Response |
|---|---|
| `GET /v1/health` | `200 {"status":"ok"}` when the API is available. Backends are checked at startup, not on each health request. |
| `GET /v1/version` | `200 {"version":"0.1.0"}` by default. Configure the value with `STREAM_MANAGER_VERSION`. |

## Streams

Live stream routes require the filesystem backend. The RTSP source must use TCP and contain one
H.264 or H.265 video track. Audio is ignored. URLs with embedded credentials are rejected.

### Attach a stream

`POST /v1/streams`

```json
{
  "sensor_id": "camera-01",
  "source_kind": "uri_source",
  "source_uri": "rtsp://camera-host:554/path"
}
```

`source_kind` is optional; if supplied, it must be `uri_source`. `sensor_id` is required. A sensor
can have only one attached stream. Success returns `201 Created`, a `Location` header, and a stream
object.

### Inspect streams

| Method and path | Description |
|---|---|
| `GET /v1/streams` | List attached streams. |
| `GET /v1/streams/{stream_id}` | Get one stream. |

The stream object includes `stream_id`, `sensor_id`, `state`, `sync_confidence`, `buffer`, `stats`,
and `creation_ts`. A new stream starts as `connecting`; it must reach `buffering` before recording.
`sync_confidence` is `ntp_synced`, `best_effort`, or `unverified`.

### Change or remove a stream

`PUT /v1/streams/{stream_id}/buffer` changes the rolling history length:

```json
{"buffer_length": 30}
```

`buffer_length` is an integer number of seconds from 1 through 300.

`DELETE /v1/streams/{stream_id}` detaches the source. The service returns `409 active_dependency`
if a recording still uses the buffer.

## Recordings

Recording routes require `STREAM_MANAGER_STORAGE_BACKEND=filesystem`. With S3 selected, they return
`503 storage_unavailable`.

### Start a recording

`POST /v1/records/start` starts one or more recordings. Select streams by `stream_ids` or sensors by
`sensor_ids`, but do not send both.

```json
{
  "stream_ids": ["stream-id"],
  "start_ts": "2026-10-05T12:00:00Z",
  "duration": 10,
  "pre_event_duration": 0,
  "metadata": {"event": "inspection"}
}
```

- `start_ts` is required, must end in `Z`, and must not be in the future. The selected stream must
  have buffer history for the requested start time minus `pre_event_duration`.
- `duration` is optional and is measured in seconds. If present, it must be greater than zero and
  the service records a fixed interval.
- Omit `duration` to record until a stop request.
- `pre_event_duration` defaults to zero and can be from 0 through 300 seconds.
- Each selector array must contain 1 through 32 unique IDs.
- `metadata` is optional user-defined JSON metadata.

Success returns `201 Created` with a `recordings` array. Each recording has an ID and starts in the
`recording` state. A completed recording reaches `ready`; a failed recording reaches `failed`.

### Stop a recording

`POST /v1/records/stop`

```json
{"recording_id": "recording-id"}
```

The request is for a recording started without `duration`. A newly accepted stop returns `202
Accepted`; then poll the recording resource until it reaches a final state.

### List and inspect recordings

| Method and path | Description |
|---|---|
| `GET /v1/records` | List and filter recordings. |
| `GET /v1/records/{recording_id}` | Get one recording and its current state. |

`GET /v1/records` supports these query parameters:

| Parameter | Meaning |
|---|---|
| `sensor_id`, `stream_id` | Filter by source. |
| `start_ts`, `end_ts`, `expiry_ts` | Filter by UTC timestamp. If both `start_ts` and `end_ts` are set, end must be later. |
| `state` | `recording`, `finalizing`, `ready`, or `failed`. |
| `metadata[key]` | Filter by a metadata field. |
| `limit` | Page size from 1 through 100; default is 20. |
| `cursor` | Opaque cursor from the previous page's `next_cursor`. |

The response contains `items` and `next_cursor`. A null `next_cursor` means there are no more pages.

### Delete a recording

`DELETE /v1/records/{recording_id}` deletes a completed or failed recording and its derived media.
Active recordings cannot be deleted. Success returns the deleted resource and ID.

## Frame and clip retrieval

The recording must exist and be in a retrievable state. The service resolves UTC timestamps through
the recording's sidecar index.

### Get a frame

`GET /v1/replays/{recording_id}/frame`

| Query parameter | Required | Values |
|---|---|---|
| `timestamp` | Yes | RFC 3339 timestamp to find. |
| `format` | No | `jpeg` (default), `jpg`, or `png`. |
| `match` | No | `nearest` (default) or `exact`. |

Send `Accept: image/jpeg`, `image/png`, or `image/*` to receive image bytes. Otherwise, when JSON is
accepted, the route returns a JSON media descriptor. `/frame/url` always returns that descriptor,
regardless of `Accept`.

### Get a clip

`GET /v1/replays/{recording_id}/clip`

| Query parameter | Required | Values |
|---|---|---|
| `timestamp_start` | Yes | RFC 3339 start time. |
| `timestamp_end` | Exactly one end value | RFC 3339 end time. |
| `duration_seconds` | Exactly one end value | A finite number greater than zero. |
| `format` | No | `mp4` (default). |

Send `Accept: video/mp4`, `video/*`, or `application/octet-stream` to receive MP4 bytes. Otherwise,
when JSON is accepted, the route returns a JSON media descriptor. `/clip/url` always returns that
descriptor. A live recording's index must include a complete sample after the requested clip end.

### Media descriptor

Both `/url` routes return a `200` response with fields like these:

```json
{
  "recording_id": "recording-id",
  "sensor_id": "camera-01",
  "media_type": "frame",
  "content_type": "image/jpeg",
  "requested_start_ts": "2026-10-05T12:00:00Z",
  "start_ts": "2026-10-05T12:00:00Z",
  "exact_match": true,
  "url": "http://localhost:18080/v1/media/<token>",
  "expiry_ts": "2026-10-05T12:05:00Z"
}
```

Clip descriptors also include `requested_end_ts` and `end_ts`. The `url` field points to the derived
media and expires at `expiry_ts`. On the filesystem backend, it is a signed `/v1/media/{token}`
capability URL. Treat it as a short-lived bearer link.

Binary frame and clip responses include `Cache-Control: private, no-store`, `X-Frame-Timestamp`, and
`X-Exact-Match`. Requests that accept neither the media type nor JSON receive `406 not_acceptable`.

### Fetch media by token

`GET /v1/media/{token}` fetches a derived object through a valid, unexpired filesystem capability
token. Invalid, expired, or unavailable media returns `404 media_not_found`.

## Common error codes

| HTTP status | Example error codes | Meaning |
|---|---|---|
| `400` | `invalid_request`, `invalid_timestamp`, `invalid_duration`, `invalid_selector` | A request field or query parameter is invalid. |
| `404` | `stream_not_found`, `record_not_found`, `recording_not_found`, `frame_not_found`, `timestamp_out_of_coverage`, `interval_not_covered` | The requested resource or time is not available. |
| `409` | `history_unavailable`, `record_not_ready`, `active_dependency` | Current state or buffer history prevents the operation. |
| `413` | `recording_too_large` | A live recording is larger than the configured extraction staging limit. |
| `415` | `unsupported_media` | The requested output format is not supported. |
| `422` | `invalid_media_index` | The sidecar index is invalid or does not match the recording. |
| `429` | `capacity_exhausted` | A recording or storage capacity limit was reached. |
| `503` | `storage_unavailable`, `extraction_failed` | Storage or media extraction is unavailable. |