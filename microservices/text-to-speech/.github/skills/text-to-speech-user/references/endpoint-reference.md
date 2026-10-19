<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Endpoint Reference

Full request/response fields for every endpoint. Base URL:
`http://127.0.0.1:8011` (default).

---

## Table of Contents

- [GET /health](#get-health)
- [GET /v1/audio/voices](#get-v1audiovoices)
- [GET /v1/model-info](#get-v1model-info)
- [GET /v1/performance](#get-v1performance)
- [POST /v1/audio/speech](#post-v1audiospeech)
- [POST /v1/audio/speech/stream](#post-v1audiospeechstream)
- [Sessions](#sessions)

---

## `GET /health`

Liveness probe. Response: `{"status": "ok"}`

## `GET /v1/audio/voices`

Returns the active model's metadata: configured model id, runtime, the list
of supported speakers, and the supported language list. Always call this
before composing a request if you are not certain which model/variant is
deployed — request validation differs by model (see
[model-and-voice-guide.md](./model-and-voice-guide.md)).

```bash
curl --noproxy '*' http://127.0.0.1:8011/v1/audio/voices
```

```json
{
  "model": "kokoro",
  "runtime": "pytorch",
  "default_speaker": "af_heart",
  "supported_speakers": ["af_heart", "am_michael", "bf_emma"],
  "default_language": "English"
}
```

Field names are `default_speaker`, `supported_speakers` (a list), and
`default_language` (singular — not a list) — do not assume the older
`speakers`/`languages` field names some OpenAI-adjacent services use.

## `GET /v1/model-info`

Returns the same model metadata payload as `/v1/audio/voices` (both are
backed by the same pipeline introspection) — present for OpenAI-adjacent
naming conventions some clients expect.

## `GET /v1/performance`

Returns aggregated latency statistics for recent synthesis calls, useful for
monitoring/capacity-planning integrations rather than end-user client code.

```json
{"latency": {"...": "..."}}
```

---

## `POST /v1/audio/speech`

Synthesize speech from text, returning either a single complete audio
payload or a JSON envelope.

| Field | Required | Description |
|-------|----------|-------------|
| `model` | No | Accepted for OpenAI API-shape compatibility; defaults to the configured service model (`models.tts.name`) if omitted, and the configured model is always used regardless of what value is sent |
| `input` | Yes | Text to synthesize, maximum 5000 characters |
| `voice` | No | Speaker name; defaults to `models.tts.default_speaker`. Behavior for an unsupported name is **model-dependent**: SpeechT5 rejects it with HTTP 400; Kokoro logs a warning and silently falls back to the configured/default Kokoro voice instead of erroring. See [model-and-voice-guide.md](./model-and-voice-guide.md) for the per-model matrix. |
| `language` | No | Only the literal value `English` is accepted; anything else returns HTTP 400 |
| `instructions` | No | Speaking-style guidance — rejected by SpeechT5, optional for Qwen `custom_voice`, required for Qwen `voice_design` |
| `response_format` | No | `wav` (default, raw `audio/wav`) or `json` (metadata + base64 WAV) |
| `device` | No | `CPU`, `GPU`, or `NPU` — overrides `models.tts.device` for this request only. Validated against the configured runtime/model and the devices actually visible inside the container; unsupported or unavailable selections are **rejected**, never silently downgraded to CPU. The first request for a given device compiles/loads a separate cached model; later requests reuse it, and cached models stay resident until the process exits. |

### `response_format=wav` (default)

Raw `audio/wav` bytes with headers:
```
X-Session-ID: <session id>
Content-Disposition: inline; filename="speech.wav"
```

```bash
curl --noproxy '*' -sS \
  -o speech.wav -w '%{http_code}\n' \
  -X POST http://127.0.0.1:8011/v1/audio/speech \
  -H 'Content-Type: application/json' \
  -d '{"model": "default", "input": "The kiosk is ready for your next request.", "response_format": "wav"}'
```

### `response_format=json`

```json
{
  "session_id": "20260909-101500-ab12",
  "model": "microsoft/speecht5_tts",
  "variant": "default",
  "voice": "Ryan",
  "language": "English",
  "duration": 2.41,
  "sampling_rate": 16000,
  "audio_base64": "UklGRi..."
}
```

> This example uses SpeechT5, a currently deployable model. Qwen3-TTS
> cannot currently run on any device — see
> [model-and-voice-guide.md](./model-and-voice-guide.md#qwen3-tts-currently-non-functional)
> before telling a user to expect a response shaped like a Qwen deployment.

Decode `audio_base64` (standard base64) to get the raw WAV bytes.

### Error Shape

Validation and runtime failures use an OpenAI-compatible error envelope:

```json
{"error": {"message": "...", "type": "invalid_request_error", "param": null, "code": "invalid_request"}}
```

| HTTP status | Meaning |
|-------------|---------|
| `422` | **Schema validation** — caught by Pydantic before the endpoint body runs, surfaced via the service's registered `RequestValidationError` handler. Covers missing/empty `input`, `input` over 5000 characters, `response_format` not `wav`/`json`, and `device` not one of `CPU`/`GPU`/`NPU`. |
| `400` | **Service-level validation** — raised as a `ValueError` inside the endpoint after the request already parsed successfully, from `request.validate_for_service()` or device resolution. Covers `language` not `English`, an unsupported `voice` (model-dependent — see [model-and-voice-guide.md](./model-and-voice-guide.md)), misused `instructions`, and a `device` value that is syntactically valid but unsupported/unavailable for the configured runtime/model. |
| `503` | Synthesis temporarily unavailable (runtime failure) |
| `500` | Unexpected internal failure |

Both `422` and `400` use the identical envelope shown above — the status
code, not the body shape, is what tells you which validation layer
rejected the request.

---

## `POST /v1/audio/speech/stream`

Phrase-level streaming variant, returns `text/event-stream`. Same request
body fields as `POST /v1/audio/speech`, **including the per-request
`device` override** — unlike some sibling speech services in this
repository, this streaming endpoint does honor `device` (validated the same
way before streaming begins — a 400 for an invalid request or an
unsupported/unavailable `device` is returned as a normal JSON error
response, not as an SSE event).

Each event is one JSON object per synthesized phrase:

```json
{
  "index": 0,
  "session_id": "20260909-101500-ab12",
  "sampling_rate": 24000,
  "duration": 1.2,
  "voice": "Ryan",
  "language": "English",
  "audio_base64": "UklGRi..."
}
```

Event sequence:
```text
data: {"index": 0, ...}

data: {"index": 1, ...}

data: [DONE]
```

Backends without incremental decoding emit exactly one phrase event before
`[DONE]` — do not assume multiple events are always available; a client
must handle the single-event case correctly.

**Edge case:** if the input text contains no pronounceable characters (for
example, only punctuation or whitespace survives normalization), the stream
emits one event:
```text
data: {"error": "Input text contains no pronounceable characters"}

data: [DONE]
```
before closing — this is a normal stream termination, not a dropped
connection; check for an `error` key in each event before treating it as
audio.

```bash
curl --noproxy '*' -N \
  -X POST http://127.0.0.1:8011/v1/audio/speech/stream \
  -H 'Content-Type: application/json' \
  -d '{"model": "default", "input": "Welcome. Please proceed to the counter.", "response_format": "wav"}'
```

Response headers include `X-Session-ID`, `Cache-Control: no-cache`, and
`X-Accel-Buffering: no` (disables upstream proxy buffering so events arrive
incrementally).

---

## Sessions

Every synthesis call is associated with a `session_id` (returned via
`X-Session-ID` on WAV responses, or the `session_id` field on JSON/streaming
responses), but **only `POST /v1/audio/speech` (non-streaming) actually
writes anything to disk**. When that deployment has
`pipeline.persist_outputs: true`, the WAV and a `generation.json` metadata
file are written server-side under `storage/<session_id>/`.
`POST /v1/audio/speech/stream` never persists its chunks to storage
— `Pipeline.synthesize_stream()` only yields audio chunks and is
documented as not writing to storage, regardless of `persist_outputs`; the
`session_id` it returns is for correlation/latency tracking only, not a
pointer to a saved file. This is a server-side persistence mechanism, not a
conversation-continuation mechanism — unlike some sibling speech services,
there is no concept of resuming or appending to a prior TTS session via a
client-supplied `session_id`.
