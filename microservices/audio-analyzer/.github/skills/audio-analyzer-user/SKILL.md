---
name: audio-analyzer-user
description: >
  Build applications with automatic speech recognition (ASR) using the Audio
  Analyzer microservice's HTTP and WebSocket API. Use this skill whenever a
  user wants to: transcribe an audio file (batch or streaming); consume
  OpenAI-compatible Server-Sent Events (`stream=true`) with the official
  OpenAI SDK; consume the NDJSON streaming endpoint; build a live voice
  application over the `/v1/realtime` WebSocket with voice activity detection
  (VAD); continue a multi-upload conversation with `session_id`; or read a
  session-level voice sentiment summary. Trigger on phrases like "transcribe
  audio", "speech to text API", "stream transcription", "realtime voice app",
  "websocket audio streaming", "build an ASR app", "OpenAI whisper-1
  compatible endpoint", "voice sentiment", "continue a transcription
  session", or "call the audio-analyzer API".
metadata:
  argument-hint: >
    Describe the ASR capability you want to build (e.g. "transcribe an
    uploaded call recording and get a sentiment summary" or "build a live
    microphone transcription client over WebSocket")
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Audio Analyzer Agent

Help a user call the Audio Analyzer API and build a voice-enabled
application with automatic speech recognition, using the right ingestion
mode for their use case.

> **Preview:** This skill is in preview — share feedback to help improve it.

## When to Use

- User wants to transcribe an uploaded audio/video file
- User wants incremental results instead of waiting for the full file —
  either OpenAI-compatible SSE (`stream=true`) or NDJSON events
- User wants a *live*, open-ended microphone/voice feed transcribed in
  real time over WebSocket
- User wants a session-level voice sentiment summary alongside a transcript
- User is integrating with an OpenAI SDK client against a self-hosted
  endpoint

## Endpoint Quick-Reference

| Need | Endpoint | Shape |
|------|----------|-------|
| One-shot transcript of a finite file | `POST /v1/audio/transcriptions` | Single JSON (or `text`/`srt`/`vtt`) |
| Incremental, OpenAI SDK-compatible | `POST /v1/audio/transcriptions` with `stream=true` | SSE: `transcript.text.delta` → `transcript.text.done` → `[DONE]` |
| Incremental, custom client | `POST /v1/audio/transcriptions/stream` | NDJSON: `transcription.chunk` → `transcription.completed` |
| Live, open-ended audio feed | `WS /v1/realtime?intent=transcription` | Bidirectional PCM16 JSON events, server-side VAD |

Default base URL: `http://127.0.0.1:8010` (container/standalone default).

## Common Mistakes to Avoid

| Mistake | Correct |
|---------|---------|
| Assuming `stream=true` works with `response_format=srt` | `stream=true` requires `response_format` to be `json` or `verbose_json`; other formats return HTTP 400 |
| Ignoring the `X-Session-ID` response header | Capture it and pass it back as `session_id` to continue the same conversation across uploads |
| Sending raw file bytes or arbitrary PCM to `/v1/realtime` | Only base64-encoded **PCM16, mono** frames via `input_audio_buffer.append`; the service does not resample |
| Expecting `/v1/audio/transcriptions/stream` to accept a `device` override | Only `POST /v1/audio/transcriptions` (single-response and `stream=true`) accepts the per-request `device` field |
| Assuming the realtime socket captures the microphone itself | The service never captures audio locally — the client owns capture and streams PCM16 frames to the service |

---

## Reference Lookup

Read a reference file only when you need the detail it contains:

| Reference | When to read |
|-----------|-------------|
| [endpoint-reference.md](./references/endpoint-reference.md) | Full request/response fields for all four ingestion modes |
| [realtime-streaming-guide.md](./references/realtime-streaming-guide.md) | WebSocket event protocol, VAD/turn-detection tuning, client code pattern |
| [integration-troubleshooting.md](./references/integration-troubleshooting.md) | Client-side mistakes: format/stream conflicts, session handling, device rejection |

## Example Prompts

| File | Covers |
|------|--------|
| [example-prompts/batch-transcription-client.md](./example-prompts/batch-transcription-client.md) | Upload a file, read the session header, get a transcript |
| [example-prompts/openai-sdk-streaming-client.md](./example-prompts/openai-sdk-streaming-client.md) | Point the official OpenAI SDK at this service with `stream=true` |
| [example-prompts/realtime-voice-app.md](./example-prompts/realtime-voice-app.md) | Build a live microphone/voice client over `/v1/realtime` |

---

## Procedure

### Execution Overview

Steps run in sequence — each step's output narrows the choices in the next one.

```
Step 0 (gather requirements — interactive)
  │
  ▼
Step 1 (pick the endpoint)
  │
  ▼
Step 2 (compose the request)
  │
  ▼
Step 3 (handle the response shape)
  │
  ▼
Step 4 (verify + next steps)
```

---

### Step 0 — Gather Requirements

| Required | What to look for | Default if absent |
|----------|-------------------|--------------------|
| **Ingestion mode** | finite file vs. live/continuous feed; need for incremental results | Ask — this decides the endpoint |
| **Client type** | raw HTTP/curl, custom app code, or an existing OpenAI SDK client | Ask if ambiguous |
| **Session continuation** | multiple uploads that should share one transcript | `false` — new session each call |
| **Sentiment** | user wants an emotional/sentiment summary alongside text | Only if `sentiment.enabled: true` on the deployed service |
| **Output format** | `json`, `text`, `verbose_json`, `srt`, `vtt` | `json` |
| **Device** | per-request `CPU`/`GPU`/`NPU` override (single-response/`stream=true` endpoint only) | service default |

If the user explicitly names a file-based vs. live use case, go straight to
Step 1. Otherwise ask.

### Step 1 — Pick the Endpoint

Use the [Endpoint Quick-Reference](#endpoint-quick-reference) table above.
Read [endpoint-reference.md](./references/endpoint-reference.md) for the
exact field list once the endpoint is chosen.

- Finite file, simplest integration → `POST /v1/audio/transcriptions`
- Finite file, need incremental UX, already using the OpenAI SDK →
  same endpoint with `stream=true`
- Finite file, incremental UX, custom (non-OpenAI-shaped) client →
  `POST /v1/audio/transcriptions/stream`
- Live/open-ended feed (microphone, telephony bridge, etc.) →
  `WS /v1/realtime?intent=transcription` — read
  [realtime-streaming-guide.md](./references/realtime-streaming-guide.md)

### Step 2 — Compose the Request

For HTTP endpoints, the request is always `multipart/form-data` with `file`
as the upload. Always surface the `session_id` handling:

```bash
curl --noproxy '*' -i \
  -F file=@recording.wav \
  http://127.0.0.1:8010/v1/audio/transcriptions
```

Capture `X-Session-ID` from the response headers if the application needs to
continue the conversation later; pass it back as the `session_id` form
field on the next upload.

For the realtime WebSocket, read
[realtime-streaming-guide.md](./references/realtime-streaming-guide.md)
before writing client code — the audio format (PCM16, mono, base64) and the
VAD/turn-detection behavior are easy to get wrong on the first attempt.

### Step 3 — Handle the Response Shape

- Single response (`stream` omitted or `false`): one JSON body with `text`
  (and `segments`, `language`, `duration` for `verbose_json`).
- SSE (`stream=true`): parse `transcript.text.delta` events for incremental
  text, `transcript.text.done` for the final text plus `language`/
  `duration`/`sentiment_summary`, then stop at `[DONE]`.
- NDJSON (`/stream`): parse `transcription.chunk` as each chunk completes,
  stop at `transcription.completed`.
- Realtime WebSocket: parse
  `conversation.item.input_audio_transcription.delta` for incremental text
  and `.completed` for the final per-utterance transcript.

**Every final answer to the user must show how the response is parsed**, not
just the request — SSE/NDJSON/WebSocket responses are easy to mishandle if
the event shape is only described rather than shown.

### Step 4 — Verify and Next Steps

```bash
curl --noproxy '*' http://127.0.0.1:8010/health
```

After a successful call, tell the user:
- Where the session's transcript persists (`storage/<session_id>/`) if they
  plan to continue the conversation later
- Whether `sentiment_summary` will actually appear (only if the deployed
  service has `sentiment.enabled: true` — this is a deployment-time setting,
  not a per-request flag)
- That `response_format` values `srt`/`vtt`/`text` are only valid when
  `stream` is omitted or `false`

If the request fails, read
[integration-troubleshooting.md](./references/integration-troubleshooting.md)
before guessing — most client-side failures map to a small, specific set of
known causes (format/stream conflict, wrong audio encoding on the WebSocket,
unsupported device override).
