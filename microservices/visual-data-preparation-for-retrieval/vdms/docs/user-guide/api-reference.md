# API Reference

<!--hide_directive```{eval-rst}
.. swagger-plugin:: api-docs/openapi.yaml
```hide_directive-->

Base URL: `http://localhost:8000/v1/dataprep` (default; the host port is configurable via `VDMS_DATAPREP_HOST_PORT`).

All endpoints return JSON unless noted. Error responses use the `DataPrepResponse` shape: `{"status": "error", "message": "<detail>"}`.

---

## `GET /health`

Liveness probe. Also reports the embedding mode and, when running in SDK mode, the SDK client load status.

**Response:**

- 200 OK (API/server mode):

  ```json
  {
      "status": "ok",
      "embedding_mode": "api"
  }
  ```

- 200 OK (SDK mode, client preloaded):

  ```json
  {
      "status": "ok",
      "embedding_mode": "sdk",
      "sdk_client_status": "preloaded",
      "model_name": "CLIP/clip-vit-b-16",
      "processing_device": "CPU",
      "sdk_use_openvino": false
  }
  ```

- 200 OK (SDK mode, client not yet loaded):

  ```json
  {
      "status": "ok",
      "embedding_mode": "sdk",
      "sdk_client_status": "not_loaded"
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
    "video_name": "clip.mp4",
    "frame_interval": 15,
    "enable_object_detection": true,
    "detection_confidence": 0.85,
    "tags": ["indoor", "machine"]
}
```

| Field                    | Type           | Required | Default | Description                                                                                         |
| ------------------------ | -------------- | -------- | ------- | --------------------------------------------------------------------------------------------------- |
| `bucket_name`            | string         | No       | config  | Minio bucket where the video is stored. Falls back to the application default bucket.               |
| `video_id`               | string         | Yes      | —       | Video directory (ID) inside the bucket.                                                             |
| `video_name`             | string         | No       | —       | Specific video filename within `video_id`. If omitted, the first MP4 found in the directory is used. |
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
      "message": "Embeddings for the video file(s) were created successfully. (Mode: api)"
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

Download or stream a video file from Minio storage.

**Query Parameters:**

| Parameter     | Type    | Required | Default | Description                                                                          |
| ------------- | ------- | -------- | ------- | ------------------------------------------------------------------------------------ |
| `video_id`    | string  | Yes      | —       | Video directory (ID) containing the video to download.                               |
| `bucket_name` | string  | No       | config  | Minio bucket. Falls back to the application default bucket.                          |
| `video_name`  | string  | No       | —       | Specific filename to download. If omitted, the first video in the directory is used. |
| `download`    | boolean | No       | `false` | Set to `true` to send `Content-Disposition: attachment` (force download).            |

**Response:**

- 200 OK — `video/mp4` stream with `Content-Disposition` header.

- 400 Bad Request — missing or invalid parameters.

- 404 Not Found — video or bucket not found.

- 500 Internal Server Error.

**Example:**

```bash
# Stream inline
curl "http://localhost:8000/v1/dataprep/videos/download?video_id=video-dir-001&video_name=clip.mp4"

# Force download
curl -O "http://localhost:8000/v1/dataprep/videos/download?video_id=video-dir-001&video_name=clip.mp4&download=true"
```

---

## `DELETE /videos/{bucket_name}/{video_id}`

Delete a specific video or all videos in a directory from Minio storage.

**Path Parameters:**

| Parameter     | Type   | Required | Description                                        |
| ------------- | ------ | -------- | -------------------------------------------------- |
| `bucket_name` | string | Yes      | Minio bucket containing the video(s) to delete.    |
| `video_id`    | string | Yes      | Video directory (ID) to delete from.               |

**Query Parameters:**

| Parameter    | Type   | Required | Description                                                                                 |
| ------------ | ------ | -------- | ------------------------------------------------------------------------------------------- |
| `video_name` | string | No       | Specific filename to delete. If omitted, **all** videos in the directory are deleted.       |

**Responses:**

- 200 OK — single file deleted:

  ```json
  {
      "status": "success",
      "message": "Video clip.mp4 deleted successfully"
  }
  ```

- 200 OK — all files in directory deleted:

  ```json
  {
      "status": "success",
      "message": "All videos in directory video-dir-001 deleted successfully"
  }
  ```

- 400 Bad Request — invalid parameters.

- 404 Not Found — bucket, video, or directory not found:

  ```json
  {
      "status": "error",
      "message": "Bucket 'my-bucket' not found"
  }
  ```

- 500 Internal Server Error.

**Example:**

```bash
# Delete a specific video
curl -X DELETE "http://localhost:8000/v1/dataprep/videos/my-bucket/video-dir-001?video_name=clip.mp4"

# Delete all videos in directory
curl -X DELETE "http://localhost:8000/v1/dataprep/videos/my-bucket/video-dir-001"
```

---

## `GET /telemetry`

Return the most recent video-processing telemetry records, newest first.

**Query Parameters:**

| Parameter | Type    | Required | Default | Description                                             |
| --------- | ------- | -------- | ------- | ------------------------------------------------------- |
| `limit`   | integer | No       | `100`   | Maximum number of records to return (1 – `TELEMETRY_MAX_RECORDS`). |

**Response:**

- 200 OK:

  ```json
  {
      "count": 1,
      "items": [
          {
              "request_id": "a1b2c3d4-...",
              "source": "/videos/upload",
              "processing_mode": "sdk",
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
                  "embedding_mode": "sdk",
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

- **Swagger UI**: `http://<HOST_IP>:<VDMS_DATAPREP_HOST_PORT>/docs`
- **ReDoc**: `http://<HOST_IP>:<VDMS_DATAPREP_HOST_PORT>/redoc`
- **OpenAPI JSON**: `http://<HOST_IP>:<VDMS_DATAPREP_HOST_PORT>/openapi.json`

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

