# Configuration

## Load Order

The service loads configuration in this order:

1. `config.yaml`
2. Environment variables with the `TEXT_TO_SPEECH__...` prefix

The same `config.yaml` is used for both Docker and standalone runs. In Docker, `config.yaml` is bind-mounted into the container, so edits on the host take effect on `docker compose restart`.

## Config File

- `config.yaml`: single source of truth for both standalone and container runs.

## Environment Variables

- `TEXT_TO_SPEECH_CONFIG_PATH`: alternate base config file (advanced)
- `TEXT_TO_SPEECH_SERVER_HOST`: host used by `python main.py`
- `TEXT_TO_SPEECH_SERVER_PORT`: port used by `python main.py`

Targeted config overrides use the `TEXT_TO_SPEECH__...` prefix.

Example:

```bash
TEXT_TO_SPEECH__MODELS__TTS__DEVICE=GPU python main.py
```

## Key Sections

- `models.tts`: model name, runtime, device, dtype, variant, speaker, English language default, cache settings
- `audio`: output format and sample width
- `pipeline.persist_outputs`: whether synthesized audio and metadata are written to storage

## Common Values

- `models.tts.runtime`: `openvino` or `pytorch`
- `models.tts.device`: `CPU` or `GPU` depending on model/runtime support. `NPU` is not currently supported by any model in this service — see [NPU](#npu) below for what actually happens if it is configured.
- `models.tts.dtype`: `int8`, `int4`, `fp16`, `fp32`
- `models.tts.model_variant`: `custom_voice` or `voice_design` for Qwen variants
- `models.tts.default_speaker`: for SpeechT5 one of `Ryan`, `Miles`, `Aaron`, `Nora`, `Elena`, `Kabir`, `Angus` (CMU Arctic ids `bdl`/`jmk`/`rms`/`clb`/`slt`/`ksp`/`awb` are accepted as aliases); for Qwen `custom_voice` a speaker name the model supports
- `models.tts.default_language`: keep this at `English`; other languages are not currently supported by the service API
- `audio.output_format`: typically `wav`

## Per-request TTS Device

`POST /v1/audio/speech` accepts an optional JSON field named `device` with
`CPU`, `GPU`, or `NPU`. When omitted, the endpoint uses `models.tts.device`.
The selected device must be supported by the configured runtime and model and
must be visible inside the service container. OpenVINO models can target visible
CPU, GPU, or NPU devices; the PyTorch runtime supports CPU and available CUDA
GPU devices; Kokoro supports CPU only.

The service rejects unsupported or unavailable selections instead of silently
falling back to CPU. The first request for a new device loads and compiles a
separate cached model; later requests reuse it. Cached models remain resident
until the process exits.

## Linux iGPU / OpenVINO GPU

To use the Intel iGPU on Linux:

- Install the required Intel/OpenVINO host GPU runtime
  (e.g. `intel-opencl-icd`, `level-zero`) on the host machine.
- Set `models.tts.device: GPU` for OpenVINO TTS.

This GPU path was validated on the Linux host setup. The container path
uses an Intel OpenVINO runtime base image plus `/dev/dri` passthrough, but
it still depends on the host having working Intel GPU support.

## NPU

Intel NPU (e.g. Intel AI Boost) is accepted as a `models.tts.device` /
per-request `device` value, but no model in this service can currently
run on it end-to-end.

Device validation (`utils/device_validation.py::resolve_tts_device`) only
runs for **per-request** `device` selections on `POST /v1/audio/speech`
and `/v1/audio/speech/stream`, and during the one-time GPU warmup
synthesis at startup. It is **not** used by `preload_models()`, which
loads the configured model directly with `models.tts.device` at startup;
the warmup synthesis that follows it does go through
`resolve_tts_device`, but a warmup failure is only logged as a warning
and does not stop the service from starting. In other words, an invalid
`models.tts.device` can still let the service start, while a per-request
`device` value is rejected immediately, before that request's model is
loaded:

- **Kokoro**: `resolve_tts_device` enforces CPU-only for Kokoro
  regardless of what is requested — checked before any runtime-specific
  logic — and rejects `NPU` with `"The configured Kokoro model supports
  only CPU inference."` for per-request selections. Because
  `preload_models()` does not call `resolve_tts_device`, Kokoro
  configured with `models.tts.device: NPU` loads normally at startup on
  CPU (Kokoro ignores the device setting), and the mismatch only
  surfaces as a logged GPU-warmup warning, not a startup failure.
- **`models.tts.runtime: pytorch`** (non-Kokoro models — SpeechT5,
  Qwen3-TTS, Parler-TTS pytorch implementations): per-request `NPU` is
  rejected with `"The PyTorch TTS runtime does not support NPU
  inference."`. PyTorch has no Intel NPU execution backend.
- **`models.tts.runtime: openvino` + SpeechT5**: device validation only
  checks that an NPU device is visible to OpenVINO
  (`ov.Core().available_devices`); it does not know that this specific
  model cannot compile for NPU. On NPU-equipped hardware the request
  passes validation but then fails when the model is compiled, with a
  raw OpenVINO compiler error (verified independently, reproduced twice):

  ```text
  Reshape node '__module.wrapped_encoder.layers.0.attention/aten::view/Reshape':
  expected exactly 1 dynamic output bound dimension, got 2
  ```

  (Verified against `openvino==2026.1.0` / `openvino-genai==2026.1.0.0`.)
  On hardware without a visible NPU device, this is instead rejected
  earlier by `resolve_tts_device` with `"... is not visible in this
  runtime."`.
- **Qwen3-TTS**: fails with a dependency error regardless of device
  (`CPU`, `GPU`, or `NPU`) — see "Qwen3-TTS dependency limitation" below.
- **Parler-TTS**: fails with a separate, unrelated error — the
  `parler-tts` package is not listed in `requirements.txt` and is not
  installed, so `utils/parler_tts_compat.py` raises
  `"parler-tts is not installed..."` on import, before any device is
  used. This is not the same issue as the Qwen3-TTS dependency conflict
  below.

Of all models, only Qwen3-TTS has NPU-specific handling in this
repository (`utils/openvino_qwen3_tts_helper.py`), which is why it is the
intended NPU-capable model. It cannot currently be exercised on any
device, including NPU, because of the dependency issue below.

### Qwen3-TTS dependency limitation

The Qwen3-TTS implementation depends on the `qwen-tts` PyPI package, which
is not currently installed by this service (see `requirements.txt`). The
only published `qwen-tts` release (`0.1.1`) requires an exact
`transformers==4.57.3` pin, while this service requires
`transformers>=5.3.0` for its own security fixes. These two requirements
cannot be satisfied at the same time, so `qwen-tts` cannot be installed
without downgrading `transformers` to a version affected by known
critical vulnerabilities. Until this upstream conflict is resolved,
Qwen3-TTS cannot be used with this service on CPU, GPU, or NPU.
