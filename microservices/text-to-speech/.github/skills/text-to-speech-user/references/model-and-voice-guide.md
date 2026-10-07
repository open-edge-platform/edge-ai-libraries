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

- `name`: `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`, `model_variant: custom_voice`.
- `voice` selects a named speaker the model supports (e.g. `Ryan`) — behaves
  like a conventional named-voice request.
- `instructions` is optional — supply speaking-style guidance if desired
  (e.g. `"Speak clearly and warmly."`); omit it for default delivery.
- `language`, if supplied, must be exactly `English`.

## Qwen3-TTS — `voice_design`

- `name`: `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice`, `model_variant: voice_design`.
- `voice` **must be omitted**. Supplying it fails validation with HTTP 400.
- `instructions` is **mandatory** — describe the desired voice there
  instead (e.g. `"A calm, low-pitched narrator voice with a slight British
  accent."`). Omitting it fails validation with HTTP 400.
- `language`, if supplied, must be exactly `English`.

---

## Field Support Matrix

| Field | Kokoro | SpeechT5 | Qwen `custom_voice` | Qwen `voice_design` |
|-------|--------|----------|----------------------|------------------------|
| `voice` | optional (voice id) | optional (named voice) | optional (named voice) | **must be omitted** |
| `instructions` | n/a (not validated) | **rejected if present** | optional | **required** |
| `language` | English only | English only | English only | English only |
| `input` max length | 5000 chars | 5000 chars | 5000 chars | 5000 chars |

Across every model, `model` in the request body is accepted for OpenAI
API-shape compatibility only — it never changes which model actually runs;
that is fixed by the deployment's `config.yaml`.
