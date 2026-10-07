<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Model and Device Configuration Reference

Covers TTS model selection, runtime/device support, precision, and voice
variants.

---

## Table of Contents

1. [Model Matrix](#model-matrix)
2. [Runtime and Device Support](#runtime-and-device-support)
3. [Precision (`dtype`)](#precision-dtype)
4. [Qwen3-TTS Variants](#qwen3-tts-variants)
5. [Shared Cache Settings](#shared-cache-settings)

---

## Model Matrix

Set via `models.tts.name` in `config.yaml`:

| Model | `name` value | Default speaker example | Notes |
|-------|--------------|--------------------------|-------|
| Kokoro | `kokoro` | `af_heart` (any `kokoro-onnx` voice id, e.g. `am_michael`, `bf_emma`) | Shipped default in `config.yaml`. Always runs on onnxruntime — `runtime` and `device` config values are **ignored** for this model. |
| SpeechT5 | `microsoft/speecht5_tts` | `Ryan` (one of 7 bundled voices) | English-only, rejects `instructions` entirely |
| Qwen3-TTS | `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` | depends on `model_variant` | Supports `instructions`; behavior branches on `model_variant` |

> [!IMPORTANT]
> The documented walkthroughs in this service's user-facing docs center on
> SpeechT5 and Qwen, but the `config.yaml` shipped with the repository
> defaults to `kokoro` with `runtime: pytorch`. Always check
> `models.tts.name` (or `GET /v1/audio/voices`) before assuming which model a
> running deployment is actually using — do not assume SpeechT5 is active
> just because it is the most-documented example.

---

## Runtime and Device Support

| Model | `runtime` | `device` |
|-------|-----------|----------|
| Kokoro | ignored — always onnxruntime | ignored — always CPU |
| SpeechT5 | `openvino` or `pytorch` | `CPU` or `GPU` |
| Qwen3-TTS | `openvino` or `pytorch` | `CPU` or `GPU` |

There is **no NPU device path** for this service — unlike some sibling
speech microservices in this repository, `models.tts.device` only accepts
`CPU` or `GPU`. Do not propose an NPU configuration for Text To Speech.

---

## Precision (`dtype`)

Permitted values: `int8`, `int4`, `fp16`, `fp32`.

| Model | Precision behavior |
|-------|---------------------|
| Kokoro | `dtype` is ignored — the released ONNX weights are used as-is |
| SpeechT5 | All four values apply |
| Qwen3-TTS | All four values apply |

> [!IMPORTANT]
> `dtype: int4` on integrated GPU is a known quality issue — it produces
> audible noise in the synthesized output. `fp16` on GPU is the validated,
> good-quality GPU precision (approximately 17s warmup, high quality
> thereafter). Never recommend `int4` for a GPU deployment without flagging
> this; recommend `fp16` or `int8` instead if the user wants reduced memory
> footprint on GPU.

---

## Qwen3-TTS Variants

`models.tts.model_variant` branches request validation:

- `custom_voice`: behaves like a conventional named-voice TTS model — the
  client's `voice` field selects a known speaker (e.g. `Ryan`).
- `voice_design`: the `voice` field must be **omitted**; the desired voice is
  instead described via the `instructions` field. A request that supplies
  both, or neither correctly, is rejected with HTTP 400 at the request-DTO
  level (`dto/speech_dto.py`) before synthesis even starts.

This is a request-shape contract, not just a config default — a deployment
operator choosing `voice_design` should expect client requests to look
different (no `voice`, mandatory `instructions`) than a `custom_voice`
deployment.

---

## Shared Cache Settings

- `models.tts.models_base_path` (default `models`): directory for
  downloaded/exported model assets, relative to the service root (or the
  mounted `models/` volume in Docker).
- `models.tts.use_local_cache` (default `true`): reuse locally cached/
  exported models instead of re-downloading/re-exporting on every start.
  Leave this `true` in production — disabling it materially slows every
  restart.
