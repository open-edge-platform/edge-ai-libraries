# API Reference

## Swagger Plugin

<!--hide_directive```{eval-rst}
.. swagger-plugin:: _assets/openapi.yaml
```hide_directive-->

Base URL: `http://localhost:8000/v1/dataprep` (default; the host port is configurable via `MM_DATAPREP_HOST_PORT`).

All endpoints return JSON unless noted. Error responses use the `DataPrepResponse` shape: `{"status": "error", "message": "<detail>"}`.

## `GET /health`

Liveness probe. Also reports the active service configuration (embedding model
and device, detection model, vector DB and storage backends, default bucket,
live-stream counts by state) so a
client can display what the service is running without a separate info call. The
configured fields are always present; `embedding_client_status` additionally
reports whether the in-process embedding client has been preloaded.

**Response:**

- 200 OK (embedding client preloaded):

  ```json
  {
      "status": "ok",
      "embedding_client_status": "preloaded",
      "model_name": "CLIP/clip-vit-b-16",
      "embedding_device": "CPU",
      "use_openvino": false,
      "detection_model": "yolox_s",
      "detection_device": "CPU",
      "vectordb_backend": "milvus",
      "vectordb_status": "ok",
      "storage_backend": "minio",
      "default_bucket_name": "video-summary",
      "live_streams_enabled": true,
      "live_streams": {"running": 2, "error": 1, "total": 3}
  }
  ```

- 200 OK (embedding client not yet loaded):

  ```json
  {
      "status": "ok",
      "embedding_client_status": "not_loaded",
      "model_name": "CLIP/clip-vit-b-16",
      "embedding_device": "CPU"
  }
  ```

## `POST /summary`

Embed a text summary for a video clip and store it in the VDMS vector database with associated metadata.

**Request Body (JSON):**

```json
{
    "bucket_name": "my-bucket",
    "video_id": "video-dir-001",
    "video_summary": "A person walking through a park at sunset.",
    "video_start_time": 10.5,
    "video_end_time": 25.0,
    "tags": ["outdoor", "person"]
}
```

| Field              | Type           | Required | Description                                                      |
| ------------------ | -------------- | -------- | ---------------------------------------------------------------- |
| `bucket_name`      | string         | Yes      | Minio bucket where the referenced video is stored.               |
| `video_id`         | string         | Yes      | Video directory (ID) inside the bucket.                          |
| `video_summary`    | string         | Yes      | Text summary to embed. Must not be empty.                        |
| `video_start_time` | float (≥ 0)    | Yes      | Start timestamp in seconds of the referenced video clip.         |
| `video_end_time`   | float          | Yes      | End timestamp in seconds. Must be greater than `video_start_time`. |
| `tags`             | list of string | No       | Tags associated with the video clip for filtering searches.      |

**Responses:**

- 201 Created:

  ```json
  {
      "status": "success",
      "message": "Video summary embedding created successfully"
  }
  ```

- 400 Bad Request — invalid time range, empty summary, or video not found in directory:

  ```json
  {
      "status": "error",
      "message": "video_end_time must be greater than video_start_time"
  }
  ```

  When the referenced video does not exist in Minio, the endpoint also returns 400 (not 404):

  ```json
  {
      "status": "error",
      "message": "Either video_id 'video-dir-001' is invalid or no video found in directory 'video-dir-001' in bucket 'my-bucket'"
  }
  ```

- 500 Internal Server Error:

  ```json
  {
      "status": "error",
      "message": "Some error ocurred at API server. Please try later!"
  }
  ```

**Example:**

```bash
curl -X POST http://localhost:8000/v1/dataprep/summary \
  -H "Content-Type: application/json" \
  -d '{
    "bucket_name": "my-bucket",
    "video_id": "video-dir-001",
    "video_summary": "A person walking through a park at sunset.",
    "video_start_time": 10.5,
    "video_end_time": 25.0,
    "tags": ["outdoor", "person"]
  }'
```

## `POST /media/process`

Process a media file (video or image) already stored in Minio. Videos are
processed by extracting frames; images are embedded directly. When object
detection is enabled, detected object crops are embedded as separate entries.

**Request Body (JSON):**

```json
{
    "bucket_name": "my-bucket",
    "video_id": "video-dir-001",
    "frame_interval": 15,
    "enable_object_detection": true,
    "detection_confidence": 0.85,
    "tags": ["indoor", "machine"]
}
```

| Field                    | Type           | Required | Default | Description                                                                                         |
| ------------------------ | -------------- | -------- | ------- | --------------------------------------------------------------------------------------------------- |
| `bucket_name`            | string         | No       | config  | Minio bucket where the video is stored. Falls back to the application default bucket.               |
| `video_id`               | string         | Yes      | —       | Video directory (ID) inside the bucket. The single video in this directory is processed.            |
| `frame_interval`         | integer (1–60) | No       | `15`    | Extract every Nth frame for processing.                                                             |
| `enable_object_detection`| boolean        | No       | `true`  | Run object detection and embed detected object crops separately.                                    |
| `detection_confidence`   | float (0.1–1.0)| No       | `0.85`  | Confidence threshold for filtering object detections.                                               |
| `tags`                   | list of string | No       | `[]`    | Tags associated with the video for filtering searches.                                              |

**Responses:**

- 201 Created:

  ```json
  {
      "status": "success",
      "message": "Embeddings for the video file(s) were created successfully."
  }
  ```

- 400 Bad Request — missing required fields or invalid parameters:

  ```json
  {
      "status": "error",
      "message": "Both bucket_name and video_id must be provided."
  }
  ```

- 404 Not Found — no video found in the specified directory:

  ```json
  {
      "status": "error",
      "message": "No video found in directory 'video-dir-001' in bucket 'my-bucket'"
  }
  ```

- 502 Bad Gateway — Minio storage error:

  ```json
  {
      "status": "error",
      "message": "Some error ocurred while accessing the Minio storage. Please try later!"
  }
  ```

- 500 Internal Server Error:

  ```json
  {
      "status": "error",
      "message": "Some error ocurred at API server. Please try later!"
  }
  ```

**Example:**

```bash
curl -X POST http://localhost:8000/v1/dataprep/media/process \
  -H "Content-Type: application/json" \
  -d '{
    "bucket_name": "my-bucket",
    "video_id": "video-dir-001",
    "frame_interval": 15,
    "enable_object_detection": true,
    "detection_confidence": 0.85
  }'
```

## `POST /media/upload`

Upload a media file (an MP4 video **or** an image), store it, and generate
embeddings. The media type is detected from the file extension / content type:
videos are processed frame-by-frame; images are embedded directly (full image
plus optional detected-object crops). Supported image formats: `.jpg`, `.jpeg`,
`.png`, `.webp`, `.bmp`, `.gif`.

**Request:** `multipart/form-data`

| Parameter                | Location | Type           | Required | Default | Description                                                                |
| ------------------------ | -------- | -------------- | -------- | ------- | -------------------------------------------------------------------------- |
| `file`                   | form     | file           | Yes      | —       | Media file to upload — an MP4 video (max 500 MB) or an image.              |
| `bucket_name`            | query    | string         | No       | config  | Destination bucket in Minio. Falls back to the application default bucket. |
| `frame_interval`         | query    | integer (1–60) | No       | `15`    | Extract every Nth frame for processing. Ignored for images.                |
| `enable_object_detection`| query    | boolean        | No       | `true`  | Run object detection and embed detected object crops separately.           |
| `detection_confidence`   | query    | float (0.1–1.0)| No       | `0.85`  | Confidence threshold for filtering object detections.                      |
| `tags`                   | query    | list of string | No       | `[]`    | Tags associated with the media for filtering searches.                     |

**Responses:**

- 201 Created:

  ```json
  {
      "status": "success",
      "message": "Embeddings for the video file(s) were created successfully."
  }
  ```

- 400 Bad Request — file is not a supported media type or fails validation:

  ```json
  {
      "status": "error",
      "message": "Only .mp4 file is supported."
  }
  ```

- 413 Request Entity Too Large — file exceeds its size limit.

- 409 Conflict — media with identical content already exists and
  `MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS` is `false`:

  ```json
  {
      "status": "error",
      "message": "A video with identical content already exists (existing video_id: 'dp_video_1784697459')."
  }
  ```

- 502 Bad Gateway — Minio storage error:

  ```json
  {
      "status": "error",
      "message": "Some error ocurred while accessing the Minio storage. Please try later!"
  }
  ```

- 500 Internal Server Error:

  ```json
  {
      "status": "error",
      "message": "Some error ocurred at API server. Please try later!"
  }
  ```

**Example:**

```bash
# Upload a video
curl -X POST "http://localhost:8000/v1/dataprep/media/upload?frame_interval=15&enable_object_detection=true" \
  -F "file=@/path/to/video.mp4"

# Upload an image
curl -X POST "http://localhost:8000/v1/dataprep/media/upload?enable_object_detection=true" \
  -F "file=@/path/to/image.jpg"
```

## Image ingestion by base64 or URL (JSON)

Images can also be ingested without a multipart upload, via a typed JSON body.
The `type` field selects the transport:

- `image_base64` — inline base64 (a bare base64 string **or** a
  `data:image/...;base64,...` data URL).
- `image_url` — a remote `http`/`https` URL the server downloads.

The real image format is sniffed from the decoded bytes (the client-declared
content type / filename is never trusted); the stored extension and content type
are derived from the sniffed format. Downloads and decodes are size-capped
(a fixed 50 MB cap) and, for URLs, time-bounded.

### `POST /media/ingest`

Ingest a single image from a typed source (synchronous, `201 Created`).

**Request:** `application/json`

| Field                     | Type    | Required | Default | Description                                              |
| ------------------------- | ------- | -------- | ------- | -------------------------------------------------------- |
| `type`                    | string  | Yes      | —       | `image_base64` or `image_url`.                           |
| `image_base64`            | string  | cond.    | —       | Required when `type=image_base64`. Base64 or data URL.   |
| `image_url`               | string  | cond.    | —       | Required when `type=image_url`. `http`/`https` only.     |
| `bucket_name`             | string  | No       | config  | Destination bucket.                                      |
| `filename`                | string  | No       | derived | Optional filename; extension is corrected to the sniffed format. |
| `enable_object_detection` | boolean | No       | `true`  | Embed detected-object crops separately.                  |
| `detection_confidence`    | float   | No       | `0.85`  | Detection confidence threshold.                          |
| `tags`                    | list    | No       | `[]`    | Tags for filtering searches.                             |

**Responses:** `201 Created` (embeddings created), `400` (bad/undecodable
source, unsupported format), `409` (duplicate content when duplicates
disallowed), `413` (image exceeds size cap), `502`/`500`.

**Examples:**

```bash
# Base64 (data URL accepted)
curl -X POST "http://localhost:8000/v1/dataprep/media/ingest" \
  -H "Content-Type: application/json" \
  -d '{"type": "image_base64", "image_base64": "data:image/png;base64,iVBORw0KGgo..."}'

# Remote URL
curl -X POST "http://localhost:8000/v1/dataprep/media/ingest" \
  -H "Content-Type: application/json" \
  -d '{"type": "image_url", "image_url": "https://example.com/cat.jpg", "tags": ["demo"]}'
```

### `POST /media/ingest/batch`

Ingest a list of typed image sources as a single asynchronous job
(`202 Accepted` + `job_id`); poll `GET /media/jobs/{job_id}` for per-item
results. Per-item error isolation applies.

**Request:** `application/json`

```json
{
  "images": [
    {"type": "image_url", "image_url": "https://example.com/a.jpg"},
    {"type": "image_base64", "image_base64": "iVBORw0KGgo..."}
  ]
}
```

## Batch Ingestion (asynchronous)

Batch ingestion processes many videos with a single request. All batch endpoints
return **`202 Accepted`** immediately with a `job_id`; the heavy processing runs
in the background so the service stays responsive. Poll
`GET /media/jobs/{job_id}` for per-item results. Batches are processed
sequentially with **per-item error isolation** — one failing video does not abort
the rest of the batch. The maximum items per batch is `MM_DATAPREP_BATCH_MAX_ITEMS`
(default 100). Batch ingestion works identically for both the MinIO and local
storage backends.

When `MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS` is `false`, `POST /media/upload/batch`
and `POST /media/ingest-dir` reject the request with **`409 Conflict`** if any
file's content is identical to an already-ingested video (content-based SHA-256
detection). `POST /media/process/batch` accepts the request and enforces the same
policy per item: each duplicate is reported as a failed item in the job status
while the non-duplicate items complete normally.

### `POST /media/upload/batch`

Upload multiple MP4 files in one multipart request.

**Request:** `multipart/form-data` — repeat the `files` field for each file.
Query params (`bucket_name`, `frame_interval`, `enable_object_detection`,
`detection_confidence`, `tags`) apply to every file in the batch.

```bash
curl -X POST "http://localhost:8000/v1/dataprep/media/upload/batch?frame_interval=15" \
  -F "files=@/path/to/video1.mp4" \
  -F "files=@/path/to/video2.mp4"
```

**202 Accepted:**

```json
{ "status": "success", "message": "Batch ingestion job accepted and is being processed.", "job_id": "…", "accepted": 2 }
```

### `POST /media/process/batch`

Process videos that already exist in storage. Provide **either** an explicit
`items` list **or** a `bucket_name` selector (optionally narrowed by `prefix`).

```bash
# Explicit list
curl -X POST http://localhost:8000/v1/dataprep/media/process/batch \
  -H "Content-Type: application/json" \
  -d '{"items":[{"video_id":"dp_video_1"},{"video_id":"dp_video_2"}]}'

# Selector: every video in a bucket whose video_id starts with "dp_"
curl -X POST http://localhost:8000/v1/dataprep/media/process/batch \
  -H "Content-Type: application/json" \
  -d '{"bucket_name":"video-summary","prefix":"dp_","frame_interval":15}'
```

Because this endpoint embeds media the caller stored itself, it is where the
duplicate-upload policy is applied for that media. With
`MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS=false`, an item whose content is already
owned by a different `video_id` fails with the duplicate message in
`GET /media/jobs/{job_id}`; re-processing the same `video_id` is still allowed,
so the `bucket_name` selector can safely re-index a bucket.

### `POST /media/ingest-dir`

Backward-compatible directory ingest. Walks `dir_path` (resolved against the
mounted `MM_DATAPREP_INGEST_DATA_ROOT`; paths are constrained to that root to
prevent traversal) and ingests every supported media file (videos and images).
Mount a host directory to `MM_DATAPREP_INGEST_DATA_ROOT` via
`MM_DATAPREP_INGEST_DATA_ROOT_HOST` in Docker Compose.

| Field                     | Type    | Required | Default | Description                                                                                     |
| ------------------------- | ------- | -------- | ------- | ----------------------------------------------------------------------------------------------- |
| `dir_path`                | string  | Yes      | —       | Directory to ingest, relative to (or inside) the ingest data root.                              |
| `recursive`               | boolean | No       | `false` | Recurse into subdirectories (the `meta` directory is always skipped).                           |
| `bucket_name`             | string  | No       | config  | Destination bucket.                                                                             |
| `frame_interval`          | integer | No       | `15`    | Extract every Nth frame (videos only).                                                          |
| `enable_object_detection` | boolean | No       | `true`  | Embed detected-object crops separately.                                                         |
| `detection_confidence`    | float   | No       | `0.85`  | Detection confidence threshold.                                                                 |
| `store_copy`              | boolean | No       | `true`  | Copy each file into the storage backend. `false` references files in place (see below).         |
| `tags`                    | list    | No       | `[]`    | Tags applied to every ingested file.                                                            |
| `metadata`                | object  | No       | `{}`    | Caller-supplied metadata applied to every ingested file (see below).                            |

**Per-file sidecar metadata.** A `meta/<basename>.json` sidecar next to a file
supplies `tags` plus any additional keys, which are persisted as user metadata
for that file (parity with, and a superset of, the legacy milvus-dataprep
directory ingest):

```json
{ "tags": ["outdoor"], "camera": "cam-7", "capture_date": 20260101 }
```

**User metadata.** Keys from the request-level `metadata` object and from
sidecars are stored as top-level, directly filterable fields alongside the
canonical metadata. Sidecar keys are per-file and therefore win over
request-level keys on a collision. Keys must be identifier-like
(`^[A-Za-z][A-Za-z0-9_]{0,63}$`), and values must be scalars or lists of scalars;
entries with unsupported values are skipped with a warning rather than failing
the ingest. Keys that collide with the canonical metadata contract (`video_id`,
`bucket_name`, `timestamp`, `tags`, ...) are **rejected with `400`**, so a value
is never silently dropped — rename the field instead.

**`source_path` and `store_copy`.** Every embedding produced by a directory
ingest records `source_path`: the origin path of the media, expressed in host
terms when `MM_DATAPREP_INGEST_DATA_ROOT_HOST` is set. Consumers that share the
ingest mount can therefore read the original file directly. Because that makes
the copy in the storage backend redundant, `store_copy: false` skips it
entirely — the file is embedded in place, with no on-disk duplication. Trade-offs
of a reference ingest:

- `GET /media` lists referenced media with `"stored": false` and its host-visible
  `source_path`, and `GET /media/download` streams it straight from the ingest
  mount (full HTTP Range support included), so it behaves like stored media over
  the API. Consumers that share the mount can also read `source_path` directly
  and skip the service entirely.
- Content markers are still written (a few bytes per file), so the duplicate
  policy applies: with `MM_DATAPREP_ALLOW_DUPLICATE_UPLOADS=false`, re-ingesting
  the same directory skips the files already embedded instead of duplicating
  them. Skipped files are reported in the submit response message and are not
  part of the job.
- The file must remain readable at that path for the lifetime of the job, and for
  as long as `GET /media/download` should be able to serve it. A reference whose
  file has been moved or deleted is omitted from `GET /media` and returns `404`
  on download.
- `DELETE /media/{bucket_name}` still removes the embeddings; original files on
  the mount are never deleted.

```bash
# Copy into storage (default)
curl -X POST http://localhost:8000/v1/dataprep/media/ingest-dir \
  -H "Content-Type: application/json" \
  -d '{"dir_path":"clips","recursive":true,"tags":["batch-1"]}'

# Reference in place, with shared metadata applied to every file
curl -X POST http://localhost:8000/v1/dataprep/media/ingest-dir \
  -H "Content-Type: application/json" \
  -d '{"dir_path":"clips","recursive":true,"store_copy":false,"metadata":{"site":"plant-a"}}'
```

### `GET /media/jobs/{job_id}`

Poll a batch job. Returns overall `state`
(`pending` | `running` | `completed` | `completed_with_errors` | `failed` |
`cancelled`), `total` / `completed` / `failed` counts, and a per-item `items`
array (`identifier`, `video_id`, `status`, `message`, `embeddings_count`).

```json
{
    "status": "success",
    "job_id": "…",
    "state": "completed_with_errors",
    "total": 3,
    "completed": 2,
    "failed": 1,
    "items": [
        { "identifier": "video1.mp4", "video_id": "dp_video_…", "status": "success", "embeddings_count": 372 },
        { "identifier": "video2.mp4", "video_id": "dp_video_…", "status": "error", "message": "No video found …" }
    ]
}
```

- 404 Not Found — unknown `job_id`.

### `DELETE /media/jobs/{job_id}`

Request cooperative cancellation of a pending/running job. Items not yet started
are marked `skipped`. Returns the current job status.

## `GET /media`

List all media (videos and images) known to the service in a bucket.

Covers both storage models: media copied into the storage backend, and media
ingested by reference (`store_copy: false`), which has no stored object and is
tracked by a path sidecar instead. Referenced entries are flagged with
`"stored": false` and carry the host-visible `source_path` of the original file.
A reference whose file is no longer readable is omitted, so every listed item can
actually be downloaded.

**Query Parameters:**

| Parameter     | Type   | Required | Default | Description                                                         |
| ------------- | ------ | -------- | ------- | ------------------------------------------------------------------- |
| `bucket_name` | string | No       | config  | Minio bucket to list. Falls back to the application default bucket. |

**Response:**

- 200 OK:

  ```json
  {
      "status": "success",
      "bucket_name": "my-bucket",
      "videos": [
          {
              "video_id": "video-dir-001",
              "video_name": "clip.mp4",
              "video_path": "video-dir-001/clip.mp4",
              "creation_ts": "2025-06-01T12:00:00+00:00",
              "stored": true
          },
          {
              "video_id": "video-dir-002",
              "video_name": "referenced.mp4",
              "video_path": "/host/data/cam1/referenced.mp4",
              "creation_ts": "2025-06-02T09:30:00+00:00",
              "stored": false,
              "source_path": "/host/data/cam1/referenced.mp4"
          }
      ]
  }
  ```

  `stored` is `false` only for media ingested by reference; `source_path` is
  omitted for stored media.

- 500 Internal Server Error.

**Example:**

```bash
curl "http://localhost:8000/v1/dataprep/media?bucket_name=my-bucket"
```

## `GET /media/download`

Download or stream a media file, whether it was copied into the active storage
backend (MinIO or local filesystem) or ingested by reference.

The endpoint advertises `Accept-Ranges: bytes` and honours the HTTP `Range`
request header, so media players (e.g. an HTML5 `<video>` element) can **seek**
without downloading the whole file — regardless of which storage backend is
configured. Byte ranges are served directly from storage (a server-side range
read on MinIO, a seek/read on the local backend), so large videos are never
fully buffered in memory.

Media ingested with `store_copy: false` has no stored object; it is resolved to
its file on the ingest mount and served from there with exactly the same Range
semantics, so callers do not need to know how a given item was ingested. The
recorded path is re-validated against `MM_DATAPREP_INGEST_DATA_ROOT` on every
request, so only files inside the mount can ever be served.

**Query Parameters:**

| Parameter     | Type    | Required | Default | Description                                                                          |
| ------------- | ------- | -------- | ------- | ------------------------------------------------------------------------------------ |
| `video_id`    | string  | Yes      | —       | Video directory (ID) containing the video to download.                               |
| `bucket_name` | string  | No       | config  | Storage bucket. Falls back to the application default bucket.                        |
| `media_path`  | string  | No       | —       | Relative path of a specific object **within** `video_id`, e.g. `segments/1790655530.mp4`. Required to address live-stream media, which is stored one or more levels below the stream prefix. |
| `download`    | boolean | No       | `false` | Set to `true` to send `Content-Disposition: attachment` (force download).            |

`media_path` is resolved strictly inside the `video_id` prefix: it must be
relative, use `/` as the separator, contain no `..` segment, and be at most four
components deep. Anything else is rejected with `400`. When it is supplied the
object must exist at exactly that path — the endpoint does not fall back to
picking some other file from the directory.

This is how a retrieval hit on a live camera is played back: a live embedding's
`video_url` has the form `<bucket>/<stream_id>/segments/<epoch>.mp4`, which maps
to `bucket_name=<bucket>`, `video_id=<stream_id>`, and
`media_path=segments/<epoch>.mp4`.

**Request Headers:**

| Header  | Description                                                                                       |
| ------- | ------------------------------------------------------------------------------------------------- |
| `Range` | Optional single byte range, e.g. `bytes=0-1023`, `bytes=1024-`, or `bytes=-500` (last 500 bytes). |

**Response:**

- 200 OK — full `video/mp4` stream with `Accept-Ranges: bytes` and `Content-Length`
  (returned when no `Range` header is sent, or when it is syntactically invalid).

- 206 Partial Content — byte range response with `Content-Range: bytes <start>-<end>/<total>`
  and a `Content-Length` equal to the range size (returned for a valid `Range` header).

- 400 Bad Request — missing or invalid parameters.

- 404 Not Found — video or bucket not found, or a referenced file that is no
  longer readable at its recorded path.

- 416 Range Not Satisfiable — the requested range lies outside the object; the
  response includes `Content-Range: bytes */<total>`.

- 500 Internal Server Error.

**Example:**

```bash
# Stream inline
curl "http://localhost:8000/v1/dataprep/media/download?video_id=video-dir-001"

# Force download
curl -O "http://localhost:8000/v1/dataprep/media/download?video_id=video-dir-001&download=true"

# Request a byte range (seek) — returns 206 Partial Content
curl -H "Range: bytes=0-1023" \
  "http://localhost:8000/v1/dataprep/media/download?video_id=video-dir-001"

# Play back a recorded live-stream segment
curl -O "http://localhost:8000/v1/dataprep/media/download\
?bucket_name=live-streams&video_id=<stream_id>&media_path=segments/1790655530.mp4"
```

## `DELETE /media/{bucket_name}`

Clear a whole bucket: delete every stored media item **and** all of the bucket's
embeddings from the active vector DB. The bucket-wide counterpart of the
per-video delete below, for resetting an ingested collection in one call.
Embeddings are removed first, so a failure never leaves orphaned vectors behind.

Vectors are deleted by `bucket_name`, so this also clears embeddings of media
that was referenced in place (`store_copy: false`) and therefore has no stored
object — a bucket that only ever held referenced media does not exist in the
storage backend at all, and the call still succeeds. Files on the ingest mount
are never deleted.

**Path Parameters:**

| Parameter     | Type   | Required | Description                                        |
| ------------- | ------ | -------- | -------------------------------------------------- |
| `bucket_name` | string | Yes      | Bucket to clear.                                   |

**Responses:**

- 200 OK — bucket cleared (also returned for an already-empty bucket):

  ```json
  {
      "status": "success",
      "message": "Bucket my-bucket cleared successfully: embeddings deleted, 12 stored media item(s) removed"
  }
  ```

- 400 Bad Request — invalid bucket name.

- 502 Bad Gateway — the storage backend or vector DB failed to delete.

- 500 Internal Server Error.

**Example:**

```bash
curl -X DELETE "http://localhost:8000/v1/dataprep/media/my-bucket"
```

## `DELETE /media/{bucket_name}/{video_id}`

Delete a video from the active storage backend **and** remove the corresponding
embeddings from the active vector DB, keeping both stores consistent. Each
`video_id` directory holds exactly one video, so this always removes the whole
video (its stored object(s) and all of its embeddings). Embeddings are removed
first, so a failure never leaves orphaned vectors behind.

**Path Parameters:**

| Parameter     | Type   | Required | Description                                        |
| ------------- | ------ | -------- | -------------------------------------------------- |
| `bucket_name` | string | Yes      | Bucket containing the video to delete.             |
| `video_id`    | string | Yes      | Video directory (ID) to delete.                    |

**Responses:**

- 200 OK — video deleted:

  ```json
  {
      "status": "success",
      "message": "Video video-dir-001 deleted successfully"
  }
  ```

- 400 Bad Request — invalid parameters.

- 404 Not Found — bucket or video not found:

  ```json
  {
      "status": "error",
      "message": "Bucket 'my-bucket' not found"
  }
  ```

- 502 Bad Gateway — the storage backend or vector DB failed to delete.

- 500 Internal Server Error.

**Example:**

```bash
# Delete the video (removes storage object(s) + vector embeddings)
curl -X DELETE "http://localhost:8000/v1/dataprep/media/my-bucket/video-dir-001"
```

## Live stream ingestion (`/media/streams`)

A live stream is a **long-lived resource**, not a request: registering one
returns immediately and a background worker keeps decoding, embedding, and
storing frames until the stream is paused or deleted. The worker reconnects on
transport failures and records playback media (N-second MP4 segments,
remuxed off the single decode connection) so a retrieval hit on a live frame
is playable.

**Identity.** Every live embedding and media object is stored under
`bucket_name = MM_DATAPREP_LIVE_STREAM_BUCKET` (default `live-streams`) and
`video_id = stream_id`. `GET /media`, `GET /media/download` (with `media_path`
for a specific segment or frame), and
`DELETE /media/{bucket_name}/{video_id}` therefore work on live data unchanged.

**Credentials.** RTSP URLs may embed `user:pass@`. Credentials are used to
connect and are stored only in the service's local registry; they are **never**
returned by these endpoints, written to the vector database, or logged. Every
response carries the redacted form (`rtsp://***@camera-1.local:554/stream1`).

**Retention.** Live ingestion grows the index forever by default. Set
`MM_DATAPREP_LIVE_RETENTION_HOURS` to a positive value to prune live embeddings
and media older than that window.

### `POST /media/streams`

Register an RTSP stream and start ingesting it.

**Request Body (JSON):**

| Field                     | Type          | Required | Default                             | Description                                                     |
| ------------------------- | ------------- | -------- | ----------------------------------- | --------------------------------------------------------------- |
| `stream_url`              | string        | Yes      | –                                   | `rtsp://` or `rtsps://` source URL.                              |
| `stream_name`             | string        | No       | derived from the redacted URL       | Friendly label.                                                  |
| `description`             | string        | No       | `null`                              | Free-text description.                                           |
| `frame_interval`          | integer       | No       | `MM_DATAPREP_FRAME_INTERVAL`        | Embed every Nth frame (1 – 60).                                  |
| `enable_object_detection` | boolean       | No       | service default                     | Generate object crops in addition to full frames.                |
| `detection_confidence`    | number        | No       | service default                     | Detection threshold (0.1 – 1.0).                                 |
| `tags`                    | array(string) | No       | `[]`                                | Applied to every embedding from this stream.                     |
| `start`                   | boolean       | No       | `true`                              | Register without starting ingestion when `false`.                |

**Responses:**

- 202 Accepted — registered:

  ```json
  {
      "status": "success",
      "message": "Live stream registered with id 2f6c1d....",
      "stream": {
          "stream_id": "2f6c1d...",
          "stream_url": "rtsp://***@camera-1.local:554/stream1",
          "stream_name": "camera-1.local:554/stream1",
          "state": "running",
          "bucket_name": "live-streams",
          "video_id": "2f6c1d...",
          "frame_interval": 15,
          "enable_object_detection": true,
          "detection_confidence": 0.85,
          "tags": ["lobby"],
          "stats": {
              "frames_processed": 0,
              "embeddings_created": 0,
              "segments_stored": 0,
              "reconnect_count": 0
          }
      }
  }
  ```

- 400 Bad Request — the URL is not a valid `rtsp(s)://` URL.
- 422 Unprocessable Entity — a processing parameter is out of range.
- 503 Service Unavailable — the concurrency limit
  (`MM_DATAPREP_LIVE_STREAM_MAX_CONCURRENT`) is reached, or live ingestion is
  disabled.

**Example:**

```bash
curl -X POST "http://localhost:8000/v1/dataprep/media/streams" \
  -H "Content-Type: application/json" \
  -d '{"stream_url": "rtsp://camera-1.local:554/stream1", "stream_name": "lobby-cam", "tags": ["lobby"]}'
```

### `POST /media/streams/batch`

Register several streams in one call. Items are processed independently: one
rejected URL does not prevent the rest from being registered.

**Request Body (JSON):** `{"items": [ <create body>, ... ]}`

**Responses:**

- 202 Accepted:

  ```json
  {
      "status": "success",
      "message": "1 live stream(s) registered, 1 rejected.",
      "accepted": 1,
      "rejected": 1,
      "items": [
          {"identifier": "rtsp://cam-a/s", "stream_id": "2f6c1d...", "status": "success", "message": "Registered."},
          {"identifier": "http://cam-b/s", "status": "error", "message": "Only rtsp:// and rtsps:// URLs are supported."}
      ]
  }
  ```

### `GET /media/streams`

List registered streams with their state and ingestion counters.

**Query Parameters:**

| Parameter | Type          | Required | Description                                                              |
| --------- | ------------- | -------- | ------------------------------------------------------------------------ |
| `state`   | string        | No       | Filter by `pending`, `starting`, `running`, `paused`, `reconnecting`, `error`, `stopped`. |
| `tags`    | array(string) | No       | Only streams carrying **all** of these tags.                             |

**Response:**

- 200 OK: `{"status": "success", "count": 2, "streams": [ ... ]}`

### `GET /media/streams/{stream_id}`

Return one stream, including `stats` (frames processed, embeddings created,
segments stored, reconnect count, uptime, last frame time) and
`last_error`.

- 200 OK / 404 Not Found.

### `PATCH /media/streams/{stream_id}`

Update a stream, or pause/resume it. Only supplied fields change.

**Request Body (JSON):**

| Field                                                              | Type          | Description                                                        |
| ------------------------------------------------------------------ | ------------- | ------------------------------------------------------------------ |
| `stream_name`, `description`                                        | string        | Descriptive fields.                                                |
| `frame_interval`, `enable_object_detection`, `detection_confidence` | –             | Processing parameters; a running stream restarts its session so the new value applies immediately. |
| `tags`                                                              | array(string) | Replaces the existing tag list.                                    |
| `state`                                                             | string        | `paused` to stop ingesting while staying registered, `running` to resume. |

- 200 OK / 400 Bad Request (unsupported transition) / 404 Not Found /
  503 Service Unavailable (resuming would exceed the concurrency limit).

**Example:**

```bash
curl -X PATCH "http://localhost:8000/v1/dataprep/media/streams/2f6c1d..." \
  -H "Content-Type: application/json" -d '{"state": "paused"}'
```

### `DELETE /media/streams/{stream_id}`

Stop ingestion and deregister the stream. Embeddings and recorded media are
**kept by default**, so historical search results keep working after a camera is
decommissioned.

**Query Parameters:**

| Parameter          | Type    | Default | Description                                        |
| ------------------ | ------- | ------- | -------------------------------------------------- |
| `purge_embeddings` | boolean | `false` | Also delete every vector generated from the stream. |
| `purge_media`      | boolean | `false` | Also delete the stream's recorded segments. |

- 200 OK:

  ```json
  {
      "status": "success",
      "message": "Live stream stopped and deregistered.",
      "stream_id": "2f6c1d...",
      "embeddings_purged": 1420,
      "media_purged": 96
  }
  ```

  A purge count of `-1` means the backend could not report an exact number.

- 404 Not Found / 502 Bad Gateway.

### `DELETE /media/streams`

Stop and deregister several streams. Accepts the same `purge_embeddings` and
`purge_media` query parameters; unknown ids are reported per item rather than
failing the call.

**Request Body (JSON):** `{"stream_ids": ["2f6c1d...", "8ab390..."]}`

### Consuming live streams from an application

Applications such as Video Search and Summarization integrate with this surface
as follows:

1. **Register** the camera with `POST /media/streams` and store the returned
   `stream_id`. Treat it as the media identity: it is also the `video_id` of
   every embedding and recorded object the stream produces.
2. **Poll** `GET /media/streams` (or a single `GET /media/streams/{stream_id}`)
   for `state`, `stats`, and `last_error` to drive a status indicator. A stream
   in `reconnecting` is self-healing; `error` requires operator action.
3. **Search** through the retrieval service as usual. Live results carry
   `is_live: true`, `live_stream_id`, `live_stream_name`, the redacted
   `stream_url`, `segment_id`, `segment_start_time`, `wall_clock_time`, and the
   external-correlation fields `sensor_id`, `capture_time`, `capture_time_source`
   and `media_owner`.
4. **Play back** a hit using its `video_url`, which points at the recorded
   segment covering the frame. It has the form
   `<bucket>/<stream_id>/segments/<epoch>.mp4`; split it into
   `bucket_name`, `video_id`, and `media_path` for
   `GET /media/download` (see that endpoint for the exact mapping).
5. **Stop** with `DELETE /media/streams/{stream_id}`, choosing whether to purge
   the accumulated embeddings and media.

## `GET /telemetry`

Return the most recent video-processing telemetry records, newest first.

**Query Parameters:**

| Parameter | Type    | Required | Default | Description                                             |
| --------- | ------- | -------- | ------- | ------------------------------------------------------- |
| `limit`   | integer | No       | `100`   | Maximum number of records to return (1 – `MM_DATAPREP_TELEMETRY_MAX_RECORDS`). |

**Response:**

- 200 OK:

  ```json
  {
      "count": 1,
      "items": [
          {
              "request_id": "a1b2c3d4-...",
              "source": "/media/upload",
              "timestamps": {
                  "requested_at": "2025-06-01T12:00:00Z",
                  "completed_at": "2025-06-01T12:00:45Z",
                  "wall_time_seconds": 45.2
              },
              "video": {
                  "bucket_name": "my-bucket",
                  "video_id": "video-dir-001",
                  "filename": "clip.mp4",
                  "frame_interval": 15,
                  "fps": 30.0,
                  "total_frames": 900,
                  "video_duration_seconds": 30.0,
                  "tags": ["outdoor"]
              },
              "config": {
                  "object_detection_enabled": true,
                  "detection_confidence": 0.85
              },
              "counts": {
                  "stream_id": 0,
                  "frames_extracted": 60,
                  "items_after_detection": 240,
                  "embeddings_stored": 240
              },
              "pipeline_stats": {},
              "stage_duration": {},
              "stage_throughput": {},
              "batches": []
          }
      ]
  }
  ```

**Example:**

```bash
curl "http://localhost:8000/v1/dataprep/telemetry?limit=10"
```

## Interactive API Documentation

When the service is running, FastAPI provides interactive docs:

- **Swagger UI**: `http://<HOST_IP>:<MM_DATAPREP_HOST_PORT>/docs`
- **ReDoc**: `http://<HOST_IP>:<MM_DATAPREP_HOST_PORT>/redoc`
- **OpenAPI JSON**: `http://<HOST_IP>:<MM_DATAPREP_HOST_PORT>/openapi.json`

With default settings:

```bash
http://<HOST_IP>:6007/docs
http://<HOST_IP>:6007/redoc
http://<HOST_IP>:6007/openapi.json
```

## Using the OpenAPI Spec with Bruno

For collection generation and API testing, import the checked-in spec:

- File: `docs/user-guide/_assets/openapi.yaml`
- Bruno: **Collections → Import OpenAPI** and select this YAML file

This file is generated from the FastAPI app and is the recommended source for reproducible Bruno collections.

## Supporting Resources

- [Get Started](./get-started.md)
- [Telemetry metrics](./telemetry-metrics.md)
