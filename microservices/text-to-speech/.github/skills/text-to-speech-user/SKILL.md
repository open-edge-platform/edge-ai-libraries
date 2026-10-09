---
name: text-to-speech-user
description: >
  Build applications with text-to-speech (TTS) synthesis using the Text To
  Speech microservice's OpenAI-compatible API. Use this skill whenever a
  user wants to: synthesize speech from text (`POST /v1/audio/speech`);
  stream phrase-level audio over Server-Sent Events
  (`POST /v1/audio/speech/stream`) for lower time-to-first-audio; discover
  available voices/models (`GET /v1/audio/voices`, `GET /v1/model-info`);
  select a voice, a per-request `device` (`CPU`/`GPU`/`NPU`), or describe a
  custom voice via `instructions` for Qwen3-TTS `voice_design` (currently
  non-functional — see the skill for the deployable alternatives); persist
  synthesized audio for later retrieval via `session_id`; or integrate an
  OpenAI-SDK-style client against a self-hosted speech endpoint. Trigger on
  phrases like "text to speech API", "synthesize speech", "generate audio
  from text", "stream TTS audio", "OpenAI speech endpoint", "voice design",
  "list available voices", "build a TTS app", or "call the text-to-speech
  API".
metadata:
  argument-hint: >
    Describe the TTS capability you want to build (e.g. "generate a WAV
    greeting for my kiosk app" or "stream phrase-level audio as it's
    synthesized")
---

<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Text To Speech Agent

Help a user call the Text To Speech API and build a voice-output
application, choosing the right endpoint and request shape for the
deployed model.

> **Preview:** This skill is in preview — share feedback to help improve it.

## When to Use

- User wants to synthesize speech from text and get back WAV audio or a
  JSON envelope
- User wants lower time-to-first-audio via phrase-level SSE streaming
- User wants to discover available voices/models before picking a `voice`
- User wants a custom-described voice (Qwen3-TTS `voice_design`) instead of
  a named speaker — note this model currently cannot be deployed at all;
  see [Common Mistakes to Avoid](#common-mistakes-to-avoid)
- User wants to persist and later retrieve synthesized audio via
  `session_id`
- User is integrating an OpenAI-SDK-style client against this self-hosted
  endpoint

## Endpoint Quick-Reference

| Need | Endpoint | Shape |
|------|----------|-------|
| One-shot speech synthesis | `POST /v1/audio/speech` | Raw `audio/wav`, or JSON with `audio_base64` when `response_format=json` |
| Lower time-to-first-audio | `POST /v1/audio/speech/stream` | SSE: one `data: {...}` event per synthesized phrase, each with its own `audio_base64`, terminated by `data: [DONE]` |
| Discover voices/model | `GET /v1/audio/voices` | JSON: model, runtime, speakers, languages |
| Model + latency introspection | `GET /v1/model-info`, `GET /v1/performance` | JSON: model metadata / latency stats |
| Liveness | `GET /health` | `{"status": "ok"}` |

Default base URL: `http://127.0.0.1:8011`.

## Common Mistakes to Avoid

| Mistake | Correct |
|---------|---------|
| Assuming `response_format` accepts `mp3`/`opus`/`aac`/`flac`/`pcm` like OpenAI's real API | Only `wav` (raw audio) and `json` (metadata + base64 WAV) are supported |
| Assuming the `model` field selects which model runs | `model` is accepted only for OpenAI API-shape compatibility — the service always uses the model configured in `config.yaml` |
| Sending `instructions` to a SpeechT5 deployment | SpeechT5 rejects `instructions` outright (HTTP 400) — it has no speaking-style control |
| Sending `voice` to a Qwen3-TTS `voice_design` deployment | `voice_design` **rejects** the `voice` field and **requires** `instructions` describing the voice instead |
| Omitting `instructions` on a Qwen3-TTS `voice_design` deployment | `instructions` is mandatory for `voice_design`; the request fails validation without it |
| Passing any `language` other than `English` | The service is English-only; any other value returns HTTP 400 |
| Assuming an unknown `voice` name silently falls back to default | **Model-dependent:** SpeechT5 returns HTTP 400 for an unknown voice; Kokoro silently substitutes the configured/default voice instead |
| Hardcoding port 8000/8080 | Default port is **`8011`** |
| Setting `device: GPU`/`NPU` and expecting a silent fallback to CPU if unsupported | The service **rejects** unsupported/unavailable device selections outright; it never downgrades silently |
| Assuming a deployment "using Qwen3-TTS" is reachable | Qwen3-TTS currently fails at **service startup** on every device due to a `qwen-tts`/`transformers` conflict — if the service won't even answer `GET /health`, this is almost certainly why, not a client bug |

---

## Reference Lookup

Read a reference file only when you need the detail it contains:

| Reference | When to read |
|-----------|-------------|
| [endpoint-reference.md](./references/endpoint-reference.md) | Full request/response fields for all endpoints, including streaming event shape |
| [model-and-voice-guide.md](./references/model-and-voice-guide.md) | Per-model (Kokoro/SpeechT5/Qwen) voice lists and request-field rules |
| [integration-troubleshooting.md](./references/integration-troubleshooting.md) | Client-side mistakes: format errors, validation 400s, empty-audio streaming edge case |

## Example Prompts

| File | Covers |
|------|--------|
| [example-prompts/basic-speech-synthesis-client.md](./example-prompts/basic-speech-synthesis-client.md) | Synthesize text to a WAV file and to a JSON envelope |
| [example-prompts/phrase-streaming-client.md](./example-prompts/phrase-streaming-client.md) | Consume the SSE phrase-streaming endpoint for low time-to-first-audio |
| [example-prompts/qwen-voice-design-client.md](./example-prompts/qwen-voice-design-client.md) | Describe a custom voice via `instructions` for Qwen3-TTS `voice_design` |

---

## Procedure

### Execution Overview

Steps run in sequence — confirming the deployed model in Step 1 determines which
request fields are valid when composing the request in Step 3.

```
Step 0 (gather requirements — interactive)
  │
  ▼
Step 1 (confirm deployed model)
  │
  ▼
Step 2 (pick the endpoint)
  │
  ▼
Step 3 (compose the request)
  │
  ▼
Step 4 (handle the response shape)
  │
  ▼
Step 5 (verify + next steps)
```

---

### Step 0 — Gather Requirements

| Required | What to look for | Default if absent |
|----------|-------------------|--------------------|
| **Text to synthesize** | The `input` content (max 5000 characters) | Must ask |
| **Latency sensitivity** | User wants audio to start sooner vs. a single complete file is fine | `false` — use the single-response endpoint |
| **Voice** | A named speaker, or a described voice style | Ask which model/variant is deployed if unclear |
| **Output shape** | Raw WAV file vs. JSON with base64 audio + metadata | `wav` |
| **Session reuse** | Whether the client needs to retrieve this audio again later | Only relevant if the deployment has `pipeline.persist_outputs: true` |
| **Device** | Per-request `CPU`/`GPU`/`NPU` override | Service default — most clients should omit this |

If the user explicitly names an endpoint or model behavior, go straight to
Step 1. Otherwise ask — especially which model/variant is deployed, since
request validation differs materially between SpeechT5, Qwen
`custom_voice`, and Qwen `voice_design`.

### Step 1 — Confirm the Deployed Model Before Composing a Request

Request validation is **model-dependent** (see
[model-and-voice-guide.md](./references/model-and-voice-guide.md)) — the
same request body can be valid for one deployed model and rejected for
another. Before writing a request body, check what is actually deployed:

```bash
curl --noproxy '*' http://127.0.0.1:8011/v1/audio/voices
```

This returns the active model, runtime, available speakers, and supported
languages.

If the service does not respond at all (not even `GET /health`), and you
were told the deployment uses Qwen3-TTS, stop and read
[integration-troubleshooting.md](./references/integration-troubleshooting.md#the-deployment-is-unreachable-because-its-configured-for-qwen3-tts)
before debugging further — this is a known, currently unresolved
deployment-side limitation, not a client issue.

### Step 2 — Pick the Endpoint

Use the [Endpoint Quick-Reference](#endpoint-quick-reference) table above.

- Simple, complete-file synthesis → `POST /v1/audio/speech`
- Lower time-to-first-audio for longer text → `POST /v1/audio/speech/stream`
  — read [endpoint-reference.md](./references/endpoint-reference.md) for the
  SSE event shape before writing a client

### Step 3 — Compose the Request

All endpoints take the same JSON body shape:

```json
{
  "model": "default",
  "input": "The kiosk is ready for your next request.",
  "voice": "Ryan",
  "language": "English",
  "instructions": null,
  "response_format": "wav",
  "device": null
}
```

Field rules that depend on the deployed model (see
[model-and-voice-guide.md](./references/model-and-voice-guide.md) for the
full matrix):
- `model`: optional — defaults to the configured service model if omitted.
  Shown above only for OpenAI API-shape parity; it never selects which
  model actually runs.
- `voice`: must be a name the deployed model actually supports — check
  `GET /v1/audio/voices` first. Omit it to use the deployment's configured
  default. An unsupported name is rejected with HTTP 400 on SpeechT5, but
  silently falls back to the default Kokoro voice (logged as a warning)
  rather than erroring.
- `instructions`: rejected for SpeechT5; optional for Qwen `custom_voice`;
  **required** (and `voice` must be omitted) for Qwen `voice_design` — but
  see the Qwen3-TTS caveat above before relying on either Qwen variant.
- `language`: omit it, or set it to exactly `"English"`.
- `device`: omit it unless the caller has a specific reason to override
  the deployment default; an unsupported or unavailable value is rejected,
  not silently downgraded to CPU. Both `POST /v1/audio/speech` and
  `POST /v1/audio/speech/stream` honor this field.

### Step 4 — Handle the Response Shape

- `response_format=wav` (default): raw `audio/wav` bytes, with
  `X-Session-ID` in the response header.
- `response_format=json`: a JSON body with `session_id`, `model`, `variant`,
  `voice`, `language`, `duration`, `sampling_rate`, and `audio_base64`.
- Streaming (`/v1/audio/speech/stream`): parse each `data: {...}` SSE event
  as one synthesized phrase (with its own `audio_base64`), and stop at
  `data: [DONE]`. If the input has no pronounceable characters, the stream
  emits a single `{"error": "..."}` event before `[DONE]` instead of audio.

**Every final answer to the user must show how the response is parsed**, not
just the request — this matters especially for the streaming endpoint,
where each event carries its own audio chunk rather than one accumulated
file.

### Step 5 — Verify and Next Steps

```bash
curl --noproxy '*' http://127.0.0.1:8011/health
```

After a successful call, tell the user:
- Whether the returned audio was saved to `storage/<session_id>/` on the
  server — only applies to `POST /v1/audio/speech` (non-streaming) when
  `pipeline.persist_outputs: true` is set on that deployment; a deployment-
  time setting, not a per-request flag. `POST /v1/audio/speech/stream`
  never persists chunks to storage, regardless of this setting.
- That the `model` field in the request does not actually select a model —
  it exists for OpenAI API-shape compatibility only
- That `response_format` is limited to `wav`/`json` — not the full OpenAI
  format list

If a request is rejected with HTTP 400 or 422, read
[integration-troubleshooting.md](./references/integration-troubleshooting.md)
before guessing — 422 means Pydantic schema validation failed before the
endpoint ran (e.g. `input` missing or over 5000 characters); 400 means a
service-level check failed after parsing succeeded (wrong `language`,
unsupported `voice`, misused `instructions`, or
missing `instructions` for `voice_design`).
