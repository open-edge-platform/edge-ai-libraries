<!-- SPDX-FileCopyrightText: (C) 2026 Intel Corporation -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

# Model and Device Configuration Reference

Covers TTS model selection, runtime/device support, precision, and voice
variants.

---

## Table of Contents

1. [Model Matrix](#model-matrix)
2. [Runtime and Device Support](#runtime-and-device-support)
3. [Known Limitations: Models That Cannot Currently Run](#known-limitations-models-that-cannot-currently-run)
4. [NPU: Accepted But Universally Non-Functional](#npu-accepted-but-universally-non-functional)
5. [Precision (`dtype`)](#precision-dtype)
6. [Qwen3-TTS Variants](#qwen3-tts-variants)
7. [Shared Cache Settings](#shared-cache-settings)

---

## Model Matrix

Set via `models.tts.name` in `config.yaml`:

| Model | `name` value | Default speaker example | Notes |
|-------|--------------|--------------------------|-------|
| Kokoro | `kokoro` | `af_heart` (any `kokoro-onnx` voice id, e.g. `am_michael`, `bf_emma`) | Shipped default in `config.yaml`. Always runs on onnxruntime — `runtime` and `device` config values are **ignored** for this model. |
| SpeechT5 | `microsoft/speecht5_tts` | `Ryan` (one of 7 bundled voices) | English-only, rejects `instructions` entirely. **`openvino` runtime only** — the PyTorch implementation is not available for this model. |
| Qwen3-TTS | `Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice` | depends on `model_variant` | ⚠️ **Currently cannot run on any device.** See [Known Limitations](#known-limitations-models-that-cannot-currently-run) before recommending this model to anyone. |

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
| SpeechT5 | `openvino` **only** (no working PyTorch implementation) | `CPU` or `GPU` |
| Qwen3-TTS | `openvino` or `pytorch` in config, but neither currently works | n/a — fails before device matters |

`models.tts.device` accepts `CPU`, `GPU`, or `NPU`, but **`NPU` is not
currently functional for any model** in this service — see
[NPU: Accepted But Universally Non-Functional](#npu-accepted-but-universally-non-functional)
for the exact per-model failure behavior before telling a developer "this
service has no NPU support" (it is accepted, just non-functional, which
changes how you should expect it to fail).

---

## Known Limitations: Models That Cannot Currently Run

### Qwen3-TTS dependency conflict

Qwen3-TTS **cannot currently be deployed on `CPU`, `GPU`, or `NPU`** — this
is a dependency conflict, not a device or configuration problem, and it
fails at **service startup**, not per-request:

- The Qwen3-TTS implementation depends on the `qwen-tts` PyPI package.
- The only published `qwen-tts` release (`0.1.1`) requires an exact pin of
  `transformers==4.57.3`.
- This service requires `transformers>=5.3.0` for its own security fixes.
- These two requirements cannot be satisfied simultaneously, so `qwen-tts`
  is not installed (not listed in `requirements.txt`).

Because `preload_models()` (`utils/preload_models.py`) loads the configured
model **at process startup** and re-raises any exception, configuring
`models.tts.name` to a Qwen3-TTS value causes `from qwen_tts import
Qwen3TTSModel` to raise `ImportError`, which `components/tts/pytorch/qwen_tts.py`
wraps as `RuntimeError("qwen-tts is not installed. Install dependencies from
requirements.txt before starting the service.")` — **the whole service fails
to start**, regardless of `device`. A developer who reports "Qwen3-TTS GPU
deployment fails" is describing this dependency failure, not a GPU-specific
problem; isolating `device: CPU` vs `GPU` will not change the outcome.

> [!IMPORTANT]
> Do not recommend deploying Qwen3-TTS in its current state. If a developer
> asks to "switch to Qwen3-TTS" or "set up voice_design", tell them this
> model cannot currently run at all and point them at SpeechT5 (openvino,
> CPU/GPU) or Kokoro (CPU) instead. The `custom_voice`/`voice_design`
> request-shape documentation in this skill remains useful for when the
> upstream conflict is resolved, but treat it as forward-looking reference,
> not a currently deployable path.

### Parler-TTS (unreferenced but present in code)

`components/tts/pytorch/parler_tts.py` and `utils/ensure_parler.py` exist in
the codebase but Parler-TTS is **not** a documented/supported
`models.tts.name` value anywhere in the user-facing docs or `config.yaml`
comments. If someone configures it anyway, it fails separately and for a
different reason than Qwen3-TTS: the `parler-tts` PyPI package is not listed
in `requirements.txt` and is not installed, so `utils/parler_tts_compat.py`
raises `"parler-tts is not installed..."` on import, before any device is
used. Do not conflate this with the Qwen3-TTS/`transformers` conflict above
— they are independent missing-dependency issues with different root
causes.

---

## NPU: Accepted But Universally Non-Functional

Intel NPU (e.g. Intel AI Boost) is accepted as a `models.tts.device` value
and as a per-request `device` value, but **no model in this service can
currently complete a request on it end-to-end**. This is a materially
different situation from "NPU is rejected as invalid" — know the difference
when explaining a failure to a developer.

Device validation lives in `utils/device_validation.py::resolve_tts_device`.
It is **only** invoked for:
1. Per-request `device` selections on `POST /v1/audio/speech` and
   `POST /v1/audio/speech/stream`.
2. The one-time GPU-warmup synthesis performed once at startup.

It is **not** invoked by `preload_models()`, which loads the configured
model directly using `models.tts.device` at startup without going through
this check. Consequence: an invalid `models.tts.device` can still let the
service **start** (the mismatch only surfaces as a logged warmup warning),
while an invalid **per-request** `device` is rejected immediately, before
that request's model is even touched. Do not assume these two code paths
behave the same way when diagnosing a report.

Per-model NPU behavior:

| Model/runtime | Per-request `NPU` behavior | `models.tts.device: NPU` at startup |
|---|---|---|
| Kokoro | Rejected immediately: `"The configured Kokoro model supports only CPU inference."` | Loads normally on CPU (device ignored by Kokoro); mismatch only logged as a warmup warning |
| `runtime: pytorch` (SpeechT5/Qwen3-TTS/Parler-TTS pytorch implementations) | Rejected immediately: `"The PyTorch TTS runtime does not support NPU inference."` (PyTorch has no Intel NPU execution backend) | Same rejection message surfaces at the startup warmup step |
| `runtime: openvino` + SpeechT5 | If no NPU is visible to OpenVINO: rejected with `"... is not visible in this runtime."` If an NPU **is** visible: passes validation, then fails at model compilation with a raw OpenVINO error (`Reshape node ... expected exactly 1 dynamic output bound dimension, got 2`) — a model limitation device validation cannot catch | Same two-stage failure, surfaced as a warmup warning instead of a request-time error |
| Qwen3-TTS (any runtime) | Fails with the dependency error from [Known Limitations](#known-limitations-models-that-cannot-currently-run) regardless of device | Same — fails at startup before device matters |

Of all models, only Qwen3-TTS has NPU-specific conversion code in this
repository (`utils/openvino_qwen3_tts_helper.py`), which is why it is the
*intended* NPU-capable model — it just cannot currently be exercised on any
device because of the dependency conflict.

---

## Precision (`dtype`)

Permitted values: `int8`, `int4`, `fp16`, `fp32`.

| Model | Precision behavior |
|-------|---------------------|
| Kokoro | `dtype` is ignored — the released ONNX weights are used as-is |
| SpeechT5 | All four values apply (via the `openvino` runtime) |
| Qwen3-TTS | Configured in `config.yaml` but moot — the model cannot load at all currently (see [Known Limitations](#known-limitations-models-that-cannot-currently-run)) |

> [!IMPORTANT]
> `dtype: int4` on integrated GPU is a known quality issue — it produces
> audible noise in the synthesized output. `fp16` on GPU is the validated,
> good-quality GPU precision (approximately 17s warmup, high quality
> thereafter). Never recommend `int4` for a GPU deployment without flagging
> this; recommend `fp16` or `int8` instead if the user wants reduced memory
> footprint on GPU.

---

## Qwen3-TTS Variants

> [!IMPORTANT]
> This section documents the request-shape contract for when Qwen3-TTS is
> deployable. Today, configuring either variant causes the **service to fail
> at startup** (see [Known Limitations](#known-limitations-models-that-cannot-currently-run)) — treat this as reference material, not a path to
> recommend right now.

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
