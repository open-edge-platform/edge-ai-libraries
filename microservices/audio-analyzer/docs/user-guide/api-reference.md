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
| `stream`          | No       | `true` streams the result as OpenAI-compatible SSE (see below).             |

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

### Streaming with `stream=true` (OpenAI-compatible SSE)

Setting `stream=true` returns `text/event-stream` instead of a single JSON
body, emitting the event shape OpenAI documents for this endpoint — so
official OpenAI SDKs can consume it directly.

| Event | Meaning |
| ----- | ------- |
| `transcript.text.delta` | Incremental text for a transcribed chunk (`delta` field). |
| `transcript.text.done`  | Final event with the complete `text`, plus `language`, `duration`, and `sentiment_summary` when available. |
| `[DONE]`                | Stream terminator sentinel. |

```bash
curl --noproxy '*' -N \
  -F file=@question_store_hours.wav \
  -F stream=true \
  http://127.0.0.1:8010/v1/audio/transcriptions
```

```text
data: {"type": "transcript.text.delta", "delta": "Hello, what time do you open?"}

data: {"type": "transcript.text.done", "text": "Hello, what time do you open?", "language": "en", "duration": 2.4}

data: [DONE]
```

`stream=true` requires `response_format` to be `json` or `verbose_json`;
other formats return HTTP 400.

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

## `WS /v1/realtime`

Continuous, live audio streaming transcription over WebSocket, shaped after
OpenAI's Realtime transcription API. Unlike the HTTP endpoints (which take a
finite upload), this accepts an open-ended audio feed and returns transcripts
utterance by utterance.

Connect to `ws://<host>:8010/v1/realtime?intent=transcription`.

Query parameters:

| Parameter    | Required | Description                                            |
| ------------ | -------- | ------------------------------------------------------ |
| `intent`     | No       | Must be `transcription` (default).                     |
| `session_id` | No       | Reuse to continue an existing session.                 |
| `language`   | No       | Language hint passed to the ASR backend.               |

Audio must be **PCM16** (signed 16-bit little-endian), mono, base64-encoded.
The default sample rate is 16000 Hz; change it with `session.update`. No
resampling is done in the socket layer — downstream ffmpeg/Whisper handle it.

### Client → server events

| Event | Payload |
| ----- | ------- |
| `session.update` | `{"session": {...}}` — set `sample_rate`, `input_audio_transcription.language`, or `turn_detection`. |
| `input_audio_buffer.append` | `{"audio": "<base64 pcm16>"}` |
| `input_audio_buffer.commit` | Force-close the current utterance and transcribe it. |
| `input_audio_buffer.clear`  | Discard buffered audio. |
| `session.close`             | Flush the buffer and close the socket. |

### Server → client events

| Event | Meaning |
| ----- | ------- |
| `transcription_session.created` / `.updated` | Current session configuration. |
| `input_audio_buffer.speech_started` / `.speech_stopped` | Server VAD detected the start/end of speech. |
| `input_audio_buffer.committed` | An utterance was closed and is being transcribed. |
| `input_audio_buffer.cleared` | Buffer discarded. |
| `conversation.item.input_audio_transcription.delta` | Incremental transcript text for an utterance. |
| `conversation.item.input_audio_transcription.completed` | Final `transcript` for the utterance (plus `language`, `sentiment_summary` when available). |
| `error` | `{"error": {"type": ..., "message": ...}}` |

### Turn detection (VAD)

By default the server splits the stream using energy-based VAD:

```json
{"type": "session.update",
 "session": {"turn_detection": {"type": "server_vad",
                                "threshold": 0.02,
                                "silence_duration_ms": 500,
                                "prefix_padding_ms": 300}}}
```

`threshold` is **normalized RMS in 0..1** (not a VAD probability). Lower it
for quiet audio; raise it for noisy environments. Set `"turn_detection": null`
to disable VAD and control boundaries yourself with
`input_audio_buffer.commit`.

Limits: 5 MB per `append` message, and any single utterance is force-committed
at 120 seconds.

A complete, runnable client example is in the
[Get Started guide](./get-started.md#verify-continuous-audio-streaming-websocket).

## Sessions
A session is identified by `session_id` and corresponds to the directory
`storage/<session_id>/`. The same id can be reused across multiple uploads to
append transcript state and (when sentiment is enabled) update the
session-level sentiment summary.

## VSS (Video Search & Summarization) compatibility

These endpoints match the contract used by VSS's `pipeline-manager`
(`sample-applications/video-search-and-summarization` in a previous Edge AI
Libraries release) and are not OpenAI-compatible.

**Route prefix.** VSS builds request URLs as `<AUDIO_HOST>/api/v1/<endpoint>`,
so these routes are served **both** unprefixed (`/models`, `/transcriptions`,
`/health`) and under `/api/v1` (`/api/v1/models`, `/api/v1/transcriptions`,
`/api/v1/health`). Both forms are identical; use `/api/v1` for VSS.

**Listen port.** VSS's Compose expects this service on container port `8000`,
while the standalone default is `8010`. Override it with the
`AUDIO_ANALYZER_SERVER_PORT` environment variable rather than editing the
image.

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
| `include_timestamps`  | No                               | `true` (VSS default) uploads the transcript as **SRT**; `false` uploads plain text. |
| `language`            | No (query param)                 | Language hint passed to the ASR backend.                            |

When a MinIO source is used, the service downloads the video from that
bucket, transcribes it, and uploads the resulting transcript back into the
**same bucket** at `{video_id}/{video_name-stem}.{srt|txt}` — this mirrors how
VSS reads the transcript directly from MinIO rather than through this API.
The extension follows `include_timestamps`: VSS sends `true` and parses the
object as SRT, so the default output is a valid SRT subtitle file.
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
  "transcript_path": "minio://my-bucket/video-1/clip.srt",
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
