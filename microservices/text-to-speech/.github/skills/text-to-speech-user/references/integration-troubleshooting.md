<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Integration Troubleshooting

Client-side integration failures, grouped by symptom.

---

## HTTP 400: "Only English is currently supported for speech synthesis"

**Cause:** `language` was set to anything other than the literal string
`English` (case-insensitive match against `models.tts.default_language`,
which is always `English` for this service).

**Fix:** Omit `language`, or set it to exactly `"English"`. This service does
not support multilingual synthesis in the current release.

---

## HTTP 400: "Unsupported voice '...'"

**Cause:** The requested `voice` is not in **SpeechT5's** supported speaker
list. SpeechT5 rejects an unknown voice outright — it does **not** silently
fall back to the configured default speaker. (Kokoro behaves differently:
an unrecognized voice there is logged as a warning and silently
substituted with the configured/default Kokoro voice instead of erroring
— if you expected a 400 and got audio instead, confirm which model is
actually deployed.)

**Fix:** Call `GET /v1/audio/voices` to get the exact list of supported
speakers for the active model/variant before composing the request. See
[model-and-voice-guide.md](./model-and-voice-guide.md) for the full
per-model voice tables.

---

## HTTP 400: "SpeechT5 does not support free-form voice instructions"

**Cause:** `instructions` was supplied while the deployed model is
SpeechT5. SpeechT5 has no speaking-style control at all.

**Fix:** Drop `instructions` entirely for a SpeechT5 deployment. Qwen3-TTS
is the model with `instructions` support, but it cannot currently be
deployed at all — see
[Qwen3-TTS: Currently Non-Functional](./model-and-voice-guide.md#qwen3-tts-currently-non-functional)
before assuming it's a reachable alternative.

---

## HTTP 400: "Qwen voice_design does not accept the voice field"

**Cause:** The deployed model is Qwen3-TTS with `model_variant:
voice_design`, and the request included a `voice` field. In today's
service, reaching this specific 400 would mean Qwen3-TTS is somehow
running — if you instead can't reach the service at all, see
[The Deployment Is Unreachable Because It's Configured for Qwen3-TTS](#the-deployment-is-unreachable-because-its-configured-for-qwen3-tts)
instead.

**Fix:** Remove `voice` from the request entirely and describe the desired
voice in `instructions` instead.

---

## HTTP 400: "Qwen voice_design requires instructions describing the desired voice"

**Cause:** Same deployment as above, but `instructions` was omitted or
empty.

**Fix:** Supply a non-empty `instructions` string describing the voice
(e.g. tone, pitch, accent, pacing). This field is mandatory for
`voice_design` — there is no default voice to fall back to.

---

## The Deployment Is Unreachable Because It's Configured for Qwen3-TTS

**Symptom:** `GET /health` (or any request) times out or refuses the
connection entirely against a deployment you were told uses Qwen3-TTS —
not an HTTP error, no response at all.

**Cause:** Qwen3-TTS currently cannot start on any device (`CPU`, `GPU`, or
`NPU`) due to a `qwen-tts`/`transformers` dependency conflict. A
Qwen3-TTS-configured service fails at startup, so it is never actually
listening — this is not a client-side problem, and no change to your
request will help.

**Fix:** This is a deployment-side limitation, not something fixable from
the client. Ask the deployment owner to switch `models.tts.name` to
SpeechT5 or Kokoro until the upstream conflict is resolved (see the
`text-to-speech-dev` skill), or confirm with them whether the service is
expected to be up at all right now.

---

## Per-Request `device` Rejected Instead of Falling Back to CPU

**Symptom:** Setting `"device": "GPU"` or `"device": "NPU"` in the request
body returns an error instead of transparently running on CPU.

**Cause:** This is deliberate — the service validates the requested
`device` against the configured runtime/model and the devices actually
visible inside the container, and **rejects** unsupported or unavailable
selections rather than silently downgrading to CPU. `NPU` in particular is
accepted as a value but is not currently functional for any model in this
service (Kokoro and the PyTorch runtime reject it outright; SpeechT5 either
rejects it or fails at model-compile time if an NPU happens to be visible).

**Fix:** This is a deployment/hardware question, not a client bug. Omit
`device` to use the deployment's configured default, or confirm with the
operator which devices are actually supported for the active model (see
the `text-to-speech-dev` skill's NPU behavior matrix).

---

## Streaming Endpoint Emits a Single Event Instead of Many

**Symptom:** `POST /v1/audio/speech/stream` returns only one `data: {...}`
event (`index: 0`) before `[DONE]`, even for longer input text.

**Cause:** This is expected for backends without incremental/phrase-level
decoding — "streaming" means "lower time-to-first-audio when available," not
"always multiple chunks." A client must correctly handle the single-event
case rather than assuming a minimum chunk count.

---

## Streaming Endpoint Emits an `error` Event Instead of Audio

**Symptom:** The stream terminates after one event shaped like
`{"error": "Input text contains no pronounceable characters"}` followed by
`[DONE]`.

**Cause:** After text normalization, the input had nothing synthesizable
left (for example, only punctuation or whitespace).

**Fix:** This is a normal, valid stream termination — not a dropped
connection or server bug. Check for an `error` key in each received event
before treating its payload as audio, and surface the message to the end
user (likely an empty or malformed `input`).

---

## Assuming `response_format` Supports MP3/Opus/AAC/FLAC/PCM

**Symptom:** A client built against OpenAI's real speech API requests
`response_format=mp3` (or similar) and gets unexpected behavior or a
validation error.

**Cause:** This service only implements two `response_format` values: `wav`
(raw audio) and `json` (metadata + base64-encoded WAV). It is OpenAI
request/response-shape compatible for the fields it supports, not a full
superset of OpenAI's format list.

**Fix:** Request `wav` or `json` only. If the application needs another
container/codec, transcode client-side after receiving the WAV payload.

---

## Assuming `model` in the Request Switches the Active Model

**Symptom:** A client sets `"model": "some-other-tts-model"` expecting the
service to switch models per request, and is confused when the response
still reflects the originally configured model.

**Cause:** `model` is accepted only for OpenAI API-shape compatibility. The
service always uses whatever is configured in `models.tts.name` in
`config.yaml` — this cannot be changed per request.

**Fix:** This is a deployment-time decision. If the application genuinely
needs multiple models available, that requires either multiple deployed
service instances or a deployment-side model change — not a client-side
parameter.

---

## Input Text Rejected for Length

**Symptom:** HTTP 422 with a message about input length (not 400).

**Cause:** `input` has a hard limit of 5000 characters, enforced directly
by the Pydantic schema (`Field(max_length=5000)`). This is a **schema**
validation failure caught before the endpoint body runs, so it returns 422
via the service's registered `RequestValidationError` handler — not the
400 used for service-level checks like `language`/`voice`/`instructions`.

**Fix:** Split longer text into multiple requests (e.g. per paragraph or
sentence group) and concatenate the resulting audio client-side, or use the
streaming endpoint to get earlier phrases back sooner while composing the
rest.
