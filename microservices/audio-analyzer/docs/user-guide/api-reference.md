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

## Supporting Resources

- Startup and deployment guides:
  - [Get Started](./get-started.md)
  - [Run with Docker](./get-started/run-container.md)
  - [Run on Host](./get-started/run-standalone.md)
- Configuration of ASR and sentiment backends:
  - [Configuration Guide](./get-started/configuration.md)
