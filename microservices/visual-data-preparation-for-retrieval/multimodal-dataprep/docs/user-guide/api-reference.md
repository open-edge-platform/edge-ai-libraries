# API Reference

<!--hide_directive```{eval-rst}
.. swagger-plugin:: api-docs/openapi.yaml
```hide_directive-->

Base URL: `http://localhost:8000/v1/dataprep` (default; the host port is configurable via `MM_DATAPREP_HOST_PORT`).

All endpoints return JSON unless noted. Error responses use the `DataPrepResponse` shape: `{"status": "error", "message": "<detail>"}`.

---

## `GET /health`

Liveness probe. Also reports the in-process embedding client load status.

**Response:**

- 200 OK (embedding client preloaded):

  ```json
  {
      "status": "ok",
      "embedding_client_status": "preloaded",
      "model_name": "CLIP/clip-vit-b-16",
      "embedding_device": "CPU",
      "use_openvino": false
  }
  ```

- 200 OK (embedding client not yet loaded):

  ```json
  {
      "status": "ok",
      "embedding_client_status": "not_loaded"
  }
  ```

---

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

---

## `POST /videos/minio`

Process a video already stored in Minio by extracting frames and generating embeddings. When object detection is enabled, detected object crops are embedded as separate entries.

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
curl -X POST http://localhost:8000/v1/dataprep/videos/minio \
  -H "Content-Type: application/json" \
  -d '{
    "bucket_name": "my-bucket",
    "video_id": "video-dir-001",
    "frame_interval": 15,
    "enable_object_detection": true,
    "detection_confidence": 0.85
  }'
```

---

## `POST /videos/upload`

Upload an MP4 video file, store it in Minio, and generate frame-based embeddings.

**Request:** `multipart/form-data`

| Parameter                | Location | Type           | Required | Default | Description                                                                |
| ------------------------ | -------- | -------------- | -------- | ------- | -------------------------------------------------------------------------- |
| `file`                   | form     | file (MP4)     | Yes      | —       | Video file to upload. MP4 format only, maximum 500 MB.                     |
| `bucket_name`            | query    | string         | No       | config  | Destination bucket in Minio. Falls back to the application default bucket. |
| `frame_interval`         | query    | integer (1–60) | No       | `15`    | Extract every Nth frame for processing.                                    |
| `enable_object_detection`| query    | boolean        | No       | `true`  | Run object detection and embed detected object crops separately.           |
| `detection_confidence`   | query    | float (0.1–1.0)| No       | `0.85`  | Confidence threshold for filtering object detections.                      |
| `tags`                   | query    | list of string | No       | `[]`    | Tags associated with the video for filtering searches.                     |

**Responses:**

- 201 Created:

  ```json
  {
      "status": "success",
      "message": "Embeddings for the video file(s) were created successfully."
  }
  ```

- 400 Bad Request — file is not MP4 or fails validation:

  ```json
  {
      "status": "error",
      "message": "Only .mp4 file is supported."
  }
  ```

- 413 Request Entity Too Large — file exceeds 500 MB limit.

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
curl -X POST "http://localhost:8000/v1/dataprep/videos/upload?frame_interval=15&enable_object_detection=true" \
  -F "file=@/path/to/video.mp4"
```

---

## Batch Ingestion (asynchronous)

Batch ingestion processes many videos with a single request. All batch endpoints
return **`202 Accepted`** immediately with a `job_id`; the heavy processing runs
in the background so the service stays responsive. Poll
`GET /videos/batch/{job_id}` for per-item results. Batches are processed
sequentially with **per-item error isolation** — one failing video does not abort
the rest of the batch. The maximum items per batch is `MM_DATAPREP_BATCH_MAX_ITEMS`
(default 100). Batch ingestion works identically for both the MinIO and local
storage backends.

### `POST /videos/upload/batch`

Upload multiple MP4 files in one multipart request.

**Request:** `multipart/form-data` — repeat the `files` field for each file.
Query params (`bucket_name`, `frame_interval`, `enable_object_detection`,
`detection_confidence`, `tags`) apply to every file in the batch.

```bash
curl -X POST "http://localhost:8000/v1/dataprep/videos/upload/batch?frame_interval=15" \
  -F "files=@/path/to/video1.mp4" \
  -F "files=@/path/to/video2.mp4"
```

**202 Accepted:**

```json
{ "status": "success", "message": "Batch ingestion job accepted and is being processed.", "job_id": "…", "accepted": 2 }
```

### `POST /videos/batch`

Process videos that already exist in storage. Provide **either** an explicit
`items` list **or** a `bucket_name` selector (optionally narrowed by `prefix`).

```bash
# Explicit list
curl -X POST http://localhost:8000/v1/dataprep/videos/batch \
  -H "Content-Type: application/json" \
  -d '{"items":[{"video_id":"dp_video_1"},{"video_id":"dp_video_2"}]}'

# Selector: every video in a bucket whose video_id starts with "dp_"
curl -X POST http://localhost:8000/v1/dataprep/videos/batch \
  -H "Content-Type: application/json" \
  -d '{"bucket_name":"video-summary","prefix":"dp_","frame_interval":15}'
```

### `POST /videos/ingest-dir`

Backward-compatible directory ingest. Walks `dir_path` (resolved against the
mounted `MM_DATAPREP_INGEST_DATA_ROOT`; paths are constrained to that root to
prevent traversal) and ingests every `.mp4` file. A `meta/<basename>.json`
sidecar next to a file may supply `tags` (parity with the legacy milvus-dataprep
directory ingest). Mount a host directory to `MM_DATAPREP_INGEST_DATA_ROOT` via
`MM_DATAPREP_INGEST_DATA_ROOT_HOST` in Docker Compose.

```bash
curl -X POST http://localhost:8000/v1/dataprep/videos/ingest-dir \
  -H "Content-Type: application/json" \
  -d '{"dir_path":"clips","recursive":true,"tags":["batch-1"]}'
```

### `GET /videos/batch/{job_id}`

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

### `DELETE /videos/batch/{job_id}`

Request cooperative cancellation of a pending/running job. Items not yet started
are marked `skipped`. Returns the current job status.

---

## `GET /videos`

List all videos stored in a Minio bucket.

**Query Parameters:**

| Parameter     | Type   | Required | Default | Description                                                    |
| ------------- | ------ | -------- | ------- | -------------------------------------------------------------- |
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
              "creation_ts": "2025-06-01T12:00:00+00:00"
          }
      ]
  }
  ```

- 500 Internal Server Error.

**Example:**

```bash
curl "http://localhost:8000/v1/dataprep/videos?bucket_name=my-bucket"
```

---

## `GET /videos/download`

Download or stream a video file from the active storage backend (MinIO or local
filesystem).

The endpoint advertises `Accept-Ranges: bytes` and honours the HTTP `Range`
request header, so media players (e.g. an HTML5 `<video>` element) can **seek**
without downloading the whole file — regardless of which storage backend is
configured. Byte ranges are served directly from storage (a server-side range
read on MinIO, a seek/read on the local backend), so large videos are never
fully buffered in memory.

**Query Parameters:**

| Parameter     | Type    | Required | Default | Description                                                                          |
| ------------- | ------- | -------- | ------- | ------------------------------------------------------------------------------------ |
| `video_id`    | string  | Yes      | —       | Video directory (ID) containing the video to download.                               |
| `bucket_name` | string  | No       | config  | Storage bucket. Falls back to the application default bucket.                        |
| `download`    | boolean | No       | `false` | Set to `true` to send `Content-Disposition: attachment` (force download).            |

**Request Headers:**

| Header  | Description                                                                                     |
| ------- | ----------------------------------------------------------------------------------------------- |
| `Range` | Optional single byte range, e.g. `bytes=0-1023`, `bytes=1024-`, or `bytes=-500` (last 500 bytes). |

**Response:**

- 200 OK — full `video/mp4` stream with `Accept-Ranges: bytes` and `Content-Length`
  (returned when no `Range` header is sent, or when it is syntactically invalid).

- 206 Partial Content — byte range response with `Content-Range: bytes <start>-<end>/<total>`
  and a `Content-Length` equal to the range size (returned for a valid `Range` header).

- 400 Bad Request — missing or invalid parameters.

- 404 Not Found — video or bucket not found.

- 416 Range Not Satisfiable — the requested range lies outside the object; the
  response includes `Content-Range: bytes */<total>`.

- 500 Internal Server Error.

**Example:**

```bash
# Stream inline
curl "http://localhost:8000/v1/dataprep/videos/download?video_id=video-dir-001"

# Force download
curl -O "http://localhost:8000/v1/dataprep/videos/download?video_id=video-dir-001&download=true"

# Request a byte range (seek) — returns 206 Partial Content
curl -H "Range: bytes=0-1023" \
  "http://localhost:8000/v1/dataprep/videos/download?video_id=video-dir-001"
```

---

## `DELETE /videos/{bucket_name}/{video_id}`

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
curl -X DELETE "http://localhost:8000/v1/dataprep/videos/my-bucket/video-dir-001"
```

---

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
              "source": "/videos/upload",
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

---

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

- File: `docs/user-guide/api-docs/openapi.yaml`
- Bruno: **Collections → Import OpenAPI** and select this YAML file

This file is generated from the FastAPI app and is the recommended source for reproducible Bruno collections.

## Supporting Resources

- [Get Started](./get-started.md)
- [Configuration Guide](./configuration.md)

