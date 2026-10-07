<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Endpoint Reference

Full request/response fields for every ingestion mode. Base URL:
`http://127.0.0.1:8010` (default).

---

## Table of Contents

- [GET /health](#get-health)
- [GET /devices](#get-devices)
- [POST /v1/audio/transcriptions](#post-v1audiotranscriptions)
- [POST /v1/audio/transcriptions/stream](#post-v1audiotranscriptionsstream)
- [WS /v1/realtime](#ws-v1realtime)
- [Sessions](#sessions)
- [VSS-Compatible Routes](#vss-compatible-routes)

---

## `GET /health`

Liveness probe. Response: `{"status": "ok"}`

## `GET /devices`

Returns detected ALSA capture devices in `hw:<card>,<device>` format. Useful
only for host microphone discovery — not required for the realtime
WebSocket, which never captures audio itself.

---

## `POST /v1/audio/transcriptions`

OpenAI-compatible, returns a single response unless `stream=true`.

| Field | Required | Description |
|-------|----------|-------------|
| `file` | Yes | Audio upload |
| `model` | No | Only accepted value is `whisper-1` |
| `session_id` | No | Reuse to continue an existing session |
| `language` | No | Language hint passed to the ASR backend |
| `prompt` | No | Accepted but currently ignored |
| `response_format` | No | `json` \| `text` \| `verbose_json` \| `srt` \| `vtt` |
| `temperature` | No | Decoding temperature |
| `stream` | No | `true` → OpenAI-compatible SSE |
| `device` | No | `CPU` \| `GPU` \| `NPU` — overrides the service-configured ASR device for this request only; diarization device is unaffected |

```bash
curl --noproxy '*' \
  -F file=@question_store_hours.wav \
  -F response_format=verbose_json \
  http://127.0.0.1:8010/v1/audio/transcriptions
```

If `session_id` is omitted, the service creates one and returns it in the
`X-Session-ID` response header. Reusing that value on a later upload
continues the same session and appends transcript state.

### `stream=true` (OpenAI-compatible SSE)

Returns `text/event-stream`:

| Event | Meaning |
|-------|---------|
| `transcript.text.delta` | Incremental text for a transcribed chunk, in `delta` |
| `transcript.text.done` | Final event: full `text`, plus `language`, `duration`, `sentiment_summary` when enabled |
| `[DONE]` | Stream terminator sentinel |

```bash
curl --noproxy '*' -N \
  -F file=@question_store_hours.wav \
  -F stream=true \
  http://127.0.0.1:8010/v1/audio/transcriptions
```

Because the event shape matches what OpenAI documents for this endpoint,
official OpenAI SDKs work unmodified — point `base_url` at this service:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8010/v1", api_key="not-used")

with open("question_store_hours.wav", "rb") as audio:
    stream = client.audio.transcriptions.create(
        model="whisper-1", file=audio, response_format="json", stream=True,
    )
    for event in stream:
        print(event)
```

> `stream=true` requires `response_format` to be `json` or `verbose_json`;
> `srt`, `vtt`, and `text` return HTTP 400 when combined with `stream=true`.

---

## `POST /v1/audio/transcriptions/stream`

NDJSON streaming variant. Uses the service-configured ASR device only — no
per-request `device` override on this endpoint.

| Field | Required | Description |
|-------|----------|-------------|
| `file` | Yes | Audio upload |
| `session_id` | No | Reuse to continue an existing session |
| `language` | No | Language hint |
| `temperature` | No | Decoding temperature |

Event types: `transcription.chunk` (per completed chunk), `transcription.completed` (once, at the end).

```bash
curl --noproxy '*' \
  -F file=@question_store_hours.wav \
  http://127.0.0.1:8010/v1/audio/transcriptions/stream
```

---

## `WS /v1/realtime`

See [realtime-streaming-guide.md](./realtime-streaming-guide.md) for the
full protocol, VAD tuning, and a runnable client. Summary:

- Connect: `ws://<host>:8010/v1/realtime?intent=transcription[&session_id=...&language=...]`
- Audio must be **PCM16** (signed 16-bit little-endian), mono, base64-encoded,
  pushed via `input_audio_buffer.append`. Default sample rate 16000 Hz,
  changeable via `session.update`. No server-side resampling.
- Limits: 5 MB per `append` message; any single utterance force-committed at
  120 seconds.

---

## Sessions

A session is identified by `session_id` and corresponds to
`storage/<session_id>/` on the service. Reusing the same id across multiple
uploads (or across the lifetime of one realtime socket) appends transcript
state and, when sentiment is enabled, updates the session-level sentiment
summary.

---

## VSS-Compatible Routes

Match the contract used by VSS's `pipeline-manager` and are **not**
OpenAI-compatible. Served both unprefixed (`/models`, `/transcriptions`,
`/health`) and under `/api/v1` (identical; use `/api/v1` for VSS).

### `GET /models` / `GET /api/v1/models`

```json
{
  "models": [{"model_id": "whisper-base", "display_name": "whisper-base", "description": "openai provider on CPU"}],
  "default_model": "whisper-base"
}
```

Always exactly one entry — this service transcribes with a single
configured model (`models.asr.name`).

### `POST /transcriptions` / `POST /api/v1/transcriptions`

Accepts a direct file upload.

| Field | Required | Description |
|-------|----------|-------------|
| `file` | Yes | Video/audio upload |
| `device` | No | Accepted for request-shape parity; informational only |
| `model_name` | No | Accepted for request-shape parity; informational only |
| `include_timestamps` | No | `true` (VSS default) → uploads transcript as SRT; `false` → plain text |
| `language` | No, query param | Language hint |

The service transcribes the upload and returns the transcript inline in the
response.

```json
{
  "status": "completed",
  "message": "Transcription completed successfully",
  "job_id": "20260720-123456-ab12",
  "transcript_path": "clip.srt",
  "video_name": "clip.mp4",
  "video_duration": 45.2
}
```

Do not reuse this endpoint's response shape for OpenAI-SDK-style clients —
use `POST /v1/audio/transcriptions` for that instead.
