# API Reference

Base URL: `http://127.0.0.1:8010` (default).

All endpoints return JSON unless noted. The transcription endpoints also set
the `X-Session-ID` response header; clients that want multi-upload sessions
should read it and pass it back as the `session_id` form field.

## `GET /health`

Liveness probe.

Response:

```json
{"status": "ok"}
```

## `GET /devices`

Returns detected ALSA capture devices in `hw:<card>,<device>` format.

## `POST /v1/audio/transcriptions`

OpenAI-compatible transcription endpoint that returns a single response.

Form fields:

| Field             | Required | Description                                                                 |
| ----------------- | -------- | --------------------------------------------------------------------------- |
| `file`            | Yes      | Audio upload.                                                               |
| `model`           | No       | Accepted value is `whisper-1`.                                              |
| `session_id`      | No       | Reuse to continue an existing session.                                      |
| `language`        | No       | Language hint passed to the ASR backend.                                    |
| `prompt`          | No       | Accepted but currently ignored.                                             |
| `response_format` | No       | One of `json`, `text`, `verbose_json`, `srt`, `vtt`.                        |
| `temperature`     | No       | Decoding temperature.                                                       |

Example:

```bash
curl --noproxy '*' \
  -F file=@question_store_hours.wav \
  -F response_format=verbose_json \
  http://127.0.0.1:8010/v1/audio/transcriptions
```

If `session_id` is omitted, the service creates one and returns it in
`X-Session-ID`. Reusing that value with another upload continues the same
session and appends transcript state.

## `POST /v1/audio/transcriptions/stream`

Streaming transcription endpoint that emits NDJSON events.

Form fields:

| Field         | Required | Description                            |
| ------------- | -------- | -------------------------------------- |
| `file`        | Yes      | Audio upload.                          |
| `session_id`  | No       | Reuse to continue an existing session. |
| `language`    | No       | Language hint.                         |
| `temperature` | No       | Decoding temperature.                  |

Event types:

- `transcription.chunk` — Emitted as each audio chunk is transcribed.
- `transcription.completed` — Emitted once, when the upload is fully
  processed.

Example:

```bash
curl --noproxy '*' \
  -F file=@question_store_hours.wav \
  http://127.0.0.1:8010/v1/audio/transcriptions/stream
```

## Sessions

A session is identified by `session_id` and corresponds to the directory
`storage/<session_id>/`. The same id can be reused across multiple uploads to
append transcript state and (when sentiment is enabled) update the
session-level sentiment summary.

## VSS (Video Search & Summarization) compatibility

These endpoints match the contract used by VSS's `pipeline-manager`
(`sample-applications/video-search-and-summarization` in a previous Edge AI
Libraries release) and are not OpenAI-compatible.

### `GET /models`

Lists ASR model(s) available for `POST /transcriptions`. This service
currently transcribes with a single configured model (`models.asr.name` in
`config.yaml`), so the response always contains exactly one entry.

```json
{
  "models": [{"model_id": "whisper-base", "display_name": "whisper-base", "description": "openai provider on CPU"}],
  "default_model": "whisper-base"
}
```

### `POST /transcriptions`

Accepts either a direct file upload **or** a MinIO source, but not both.

Form fields:

| Field                 | Required                        | Description                                                        |
| --------------------- | -------------------------------- | ------------------------------------------------------------------- |
| `file`                | If not using MinIO source        | Video/audio upload.                                                 |
| `minio_bucket`        | If not uploading a file          | MinIO bucket containing the source video.                           |
| `video_id`            | If not uploading a file          | Prefix/ID of the video object within the bucket.                    |
| `video_name`          | If not uploading a file          | Name of the video object within the bucket.                         |
| `device`              | No                               | Accepted for request-shape parity; currently informational only.    |
| `model_name`          | No                               | Accepted for request-shape parity; currently informational only.    |
| `include_timestamps`  | No                               | Accepted for request-shape parity.                                  |
| `language`            | No (query param)                 | Language hint passed to the ASR backend.                            |

When a MinIO source is used, the service downloads the video from that
bucket, transcribes it, and uploads the resulting transcript back into the
**same bucket** at `{video_id}/{video_name-stem}.txt` — this mirrors how VSS
reads the transcript directly from MinIO rather than through this API.
MinIO connection details are configured via `minio.endpoint` /
`minio.access_key` / `minio.secret_key` / `minio.secure` in `config.yaml`
(or `AUDIO_ANALYZER__MINIO__*` env vars). If `minio.endpoint` is empty and a
MinIO source is requested, the endpoint returns `503`.

Response:

```json
{
  "status": "completed",
  "message": "Transcription completed successfully",
  "job_id": "20260720-123456-ab12",
  "transcript_path": "minio://my-bucket/video-1/clip.txt",
  "video_name": "clip.mp4",
  "video_duration": 45.2
}
```

Example (MinIO source):

```bash
curl --noproxy '*' \
  -F minio_bucket=my-bucket \
  -F video_id=video-1 \
  -F video_name=clip.mp4 \
  http://127.0.0.1:8010/transcriptions
```

## Supporting Resources

- Startup and deployment guides:
  - [Get Started](./get-started.md)
  - [Run with Docker](./get-started/run-container.md)
  - [Run on Host](./get-started/run-standalone.md)
- Configuration of ASR and sentiment backends:
  - [Configuration Guide](./get-started/configuration.md)
