<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Model and Voice Guide

Per-model request-field rules. Always confirm the active model/variant with
`GET /v1/audio/voices` before relying on this table for a specific
deployment — request validation is model-dependent, and the same JSON body
can be valid for one deployed model and rejected for another.

---

## Table of Contents

- [Kokoro](#kokoro)
- [SpeechT5](#speecht5)
- [Qwen3-TTS — `custom_voice`](#qwen3-tts--custom_voice)
- [Qwen3-TTS — `voice_design`](#qwen3-tts--voice_design)
- [Qwen3-TTS: Currently Non-Functional](#qwen3-tts-currently-non-functional)
- [Field Support Matrix](#field-support-matrix)

---

## Kokoro

- `name`: `kokoro` (the repository's shipped default).
- Voices: `af_heart` (default) and any voice id supported by `kokoro-onnx`,
  e.g. `am_michael`, `bf_emma`.
- Always runs on onnxruntime/CPU regardless of `runtime`/`device` config.
- English-only.

## SpeechT5

- `name`: `microsoft/speecht5_tts`.
- Seven bundled voices (human-readable names, with CMU Arctic aliases):

  | Voice name | CMU Arctic alias |
  |------------|-------------------|
  | `Ryan` | `bdl` |
  | `Miles` | `jmk` |
  | `Aaron` | `rms` |
  | `Nora` | `clb` |
  | `Elena` | `slt` |
  | `Kabir` | `ksp` |
  | `Angus` | `awb` |

- Omitting `voice` uses `models.tts.default_speaker`.
- An unknown voice name returns HTTP 400 — it does not silently fall back to
  the default.
- `instructions` is **rejected outright** — SpeechT5 has no speaking-style
  control. Any non-empty `instructions` value fails validation with HTTP
  400.
- `language`, if supplied, must be exactly `English`.

## Qwen3-TTS — `custom_voice`

> [!IMPORTANT]
> Read [Qwen3-TTS: Currently Non-Functional](#qwen3-tts-currently-non-functional)
> before helping anyone build against this variant — no deployment of it is
> currently reachable.

- `name`: `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`, `model_variant: custom_voice`.
- `voice` selects a named speaker the model supports (e.g. `Ryan`) — behaves
  like a conventional named-voice request.
- `instructions` is optional — supply speaking-style guidance if desired
  (e.g. `"Speak clearly and warmly."`); omit it for default delivery.
- `language`, if supplied, must be exactly `English`.

## Qwen3-TTS — `voice_design`

> [!IMPORTANT]
> Read [Qwen3-TTS: Currently Non-Functional](#qwen3-tts-currently-non-functional)
> before helping anyone build against this variant — no deployment of it is
> currently reachable.

- `name`: `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`, `model_variant: voice_design`.
- `voice` **must be omitted**. Supplying it fails validation with HTTP 400.
- `instructions` is **mandatory** — describe the desired voice there
  instead (e.g. `"A calm, low-pitched narrator voice with a slight British
  accent."`). Omitting it fails validation with HTTP 400.
- `language`, if supplied, must be exactly `English`.

---

## Qwen3-TTS: Currently Non-Functional

Both Qwen3-TTS variants above document the **request-shape contract** for
when this model is deployable. Today, it is not: a deployment configured
with `models.tts.name: Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` **fails to
start at all**, on any device (`CPU`, `GPU`, or `NPU`), because the
required `qwen-tts` PyPI package pins `transformers==4.57.3` while this
service requires `transformers>=5.3.0` for security fixes — the two
cannot be installed together.

Practical implications for building a client:

- If you are told "the deployment uses Qwen3-TTS" and the service does not
  respond to `GET /health` at all, this is almost certainly **why** — it is
  not a client bug, and no change to your request body will fix it.
- This is a service-startup failure, not a per-request error. You will not
  see an HTTP 400 for a bad `voice`/`instructions` combination against a
  Qwen3-TTS deployment, because the service never comes up far enough to
  accept requests.
- If instruction-driven voice control is a hard requirement today, it is
  not available on this service — Kokoro and SpeechT5 are the currently
  deployable models, and neither supports `instructions`
  (SpeechT5 rejects it outright; Kokoro ignores it).

---

## Field Support Matrix

| Field | Kokoro | SpeechT5 | Qwen `custom_voice` | Qwen `voice_design` |
|-------|--------|----------|----------------------|------------------------|
| `voice` | optional (voice id) | optional (named voice) | optional (named voice) | **must be omitted** |
| `instructions` | n/a (not validated) | **rejected if present** | optional | **required** |
| `language` | English only | English only | English only | English only |
| `device` | `CPU` only (GPU/NPU rejected) | `CPU`/`GPU` (NPU rejected or fails at compile time) | n/a — model cannot currently load | n/a — model cannot currently load |
| `input` max length | 5000 chars | 5000 chars | 5000 chars | 5000 chars |

Across every model, `model` in the request body is accepted for OpenAI
API-shape compatibility only — it never changes which model actually runs;
that is fixed by the deployment's `config.yaml`.
