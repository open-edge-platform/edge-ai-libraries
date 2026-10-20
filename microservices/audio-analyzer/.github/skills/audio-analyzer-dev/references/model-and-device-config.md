<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Model and Device Configuration Reference

Covers ASR provider/device selection, precision, diarization, sentiment, and
the per-request device override.

---

## Table of Contents

1. [ASR Provider/Device Matrix](#asr-providerdevice-matrix)
2. [Model Selection and Precision](#model-selection-and-precision)
3. [Per-Request Device Override](#per-request-device-override)
4. [Speaker Diarization Setup](#speaker-diarization-setup)
5. [Voice Sentiment Setup](#voice-sentiment-setup)
6. [Hallucination and Repetition Filtering](#hallucination-and-repetition-filtering)

---

## ASR Provider/Device Matrix

Configured via `models.asr.provider` and `models.asr.device` in
`config.yaml`:

| Provider | CPU | GPU | NPU | Notes |
|----------|-----|-----|-----|-------|
| `openai` | ✅ | ❌ | ❌ | `openai-whisper`, downloads PyTorch Whisper weights on first use |
| `whispercpp` | ✅ | ❌ | ❌ | Downloads matching `ggml` model under `models/whispercpp/...` |
| `openvino` | ✅ | ✅ | ✅ | Exports to OpenVINO IR under `models/openvino/...` |

An invalid combination (e.g. `provider: openai` with `device: GPU`) fails
startup immediately with a clear validation error — it never silently falls
back to CPU.

`app.use_ov_genai: True` (default) selects the OpenVINO GenAI pipeline
implementation for the `openvino` provider.

---

## Model Selection and Precision

`models.asr.name`: one of `whisper-tiny`, `whisper-base`, `whisper-small`,
`whisper-medium`, `whisper-large`.

`models.asr.weight_format`:
- For `openvino`: export precision — `int8`, `fp16`, or `null` (framework
  default).
- For `whispercpp`: quantization — `null`, `q5`, `q5_0`, `q5_1`, `q8`, `q8_0`,
  `int5`, `int8`.

> [!IMPORTANT]
> `whisper-large` is a confirmed NPU driver/firmware limitation on current
> hardware (Intel Core Ultra / architecture 3720): it compiles successfully
> (~200s) but fails at inference time with `ZE_RESULT_ERROR_UNINITIALIZED` at
> `pfnAppendGraphExecute`. `whisper-tiny`/`base`/`small`/`medium` all pass NPU
> inference validation on the same hardware. Use `CPU` or `GPU` for
> `whisper-large` until a driver update resolves this (the exclusion list
> lives in `utils/openvino_runtime_validation.py` as
> `_OPENVINO_NPU_INFERENCE_UNSUPPORTED`).

Decoder/provider-specific fields: `beam_size`, `best_of`, `word_timestamps`,
`threads` apply only to `openai`/`whispercpp`. `temperature` applies to all
providers.

---

## Per-Request Device Override

`POST /v1/audio/transcriptions` (both single-response and `stream=true`
forms) accepts an optional multipart `device` field (`CPU`/`GPU`/`NPU`) that
overrides `models.asr.device` for that request only. The streaming NDJSON
endpoint (`/v1/audio/transcriptions/stream`), the realtime WebSocket, and the
VSS-compatible routes always use the service-configured device.

Operational implications for a deployment:
- The first request for a given device is slower — the model must be
  compiled/loaded for that device before inference.
- Models for every device that has been requested stay cached in memory
  until process exit, so enabling per-request overrides across multiple
  devices increases memory footprint. Size `audio_analyzer_models` and host
  RAM accordingly if you expect clients to mix devices.
- Unsupported or unavailable devices are rejected outright — never silently
  downgraded to CPU.
- `models.diarization.device` is independent and is not changed by the ASR
  `device` override.

---

## Speaker Diarization Setup

Enabled via `models.asr.diarization: true`. Requires:

1. A Hugging Face account and access token
   (https://huggingface.co/settings/tokens).
2. One-time acceptance of the
   [Pyannote speaker-diarization model license](https://huggingface.co/pyannote/speaker-diarization-community-1).
3. `HF_TOKEN` set — in `.env` for Compose, or exported in the shell before
   `python main.py` for standalone.

If the token is missing or the gate was not accepted, the service **does
not crash** — it logs a warning and disables diarization for that session
only, while the rest of the service keeps running normally. This is a
soft-fail by design; do not treat it as a hard deployment blocker unless
diarization output is a hard requirement.

Related config (`models.diarization` section):
- `provider: huggingface`, `name: pyannote/speaker-diarization-community-1`
- `device`: `CPU` | `GPU` | `NPU`
- `min_speakers` / `max_speakers`: tune for the expected scenario (defaults
  assume a kiosk-style 1 customer + 1 staff member per chunk)
- `identity.enabled`: cross-chunk primary-speaker resolution reusing
  embeddings already computed during diarization clustering — no extra
  model load. Tune `similarity_threshold`, `lock_min_duration_sec`, and
  `session_ttl_seconds` for the deployment's expected session length.

---

## Voice Sentiment Setup

Enabled via `sentiment.enabled: true`. Runs in parallel with ASR per chunk
(via a `ThreadPoolExecutor` inside `pipeline.py`) and aggregates a
session-level summary.

Key fields:
- `sentiment.model`: default `speechbrain/emotion-recognition-wav2vec2-IEMOCAP`;
  any compatible Hugging Face model works.
- `sentiment.provider`: `openvino` or `pytorch`.
- `sentiment.device`: `CPU` or `GPU` (OpenVINO export only).
- `sentiment.weight_format`: optional OpenVINO export precision.
- `sentiment.recency_weight`: 0.0 (equal weight across chunks) to 1.0 (last
  chunk only) — tune higher for kiosk/escalation-detection scenarios.
- `sentiment.peak_label`: the label to watch for peak/escalation detection
  (e.g. `angry`).

Enabling sentiment adds a second model load at startup and parallel
inference per chunk — budget extra memory and a slightly higher per-chunk
latency when sizing the deployment.

---

## Hallucination and Repetition Filtering

Not device-specific, but relevant when tuning a deployment for a noisy
environment (e.g. kiosk microphones):

- `no_speech_threshold` / `logprob_threshold`: native `openai`/`whispercpp`
  confidence signals; OpenVINO GenAI pipelines do not expose these and skip
  this filter.
- `hallucination_phrase_filter` + `hallucination_phrases`: backend-agnostic —
  drops any segment whose entire text matches a known hallucinated phrase
  (e.g. "thank you", "subscribe"). This is the only filter that also covers
  OpenVINO GenAI.
- `repetition_penalty`: post-processing dedup of repeated n-grams and
  duplicate segments; `1.0` disables it, values above `1.0` enable it for
  all providers.

Tune these more aggressively for live/noisy microphone deployments and more
conservatively for clean studio-quality recordings.
