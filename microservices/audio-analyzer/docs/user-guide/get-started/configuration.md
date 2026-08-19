# Configuration

## Load Order

The service loads configuration in this order:

1. `config.yaml`
2. Environment variables with the `AUDIO_ANALYZER__...` prefix

The same `config.yaml` is used for both Docker and standalone runs. In Docker, `config.yaml` is bind-mounted into the container, so edits on the host take effect on `docker compose restart`.

## Config File

- `config.yaml`: single source of truth for both standalone and container runs.

## Environment Variables

- `AUDIO_ANALYZER_CONFIG_PATH`: alternate base config file (advanced)
- `AUDIO_ANALYZER_ENV_FILE`: optional `.env` file to preload before config parsing
- `AUDIO_ANALYZER_SERVER_HOST`: host used by `python main.py`
- `AUDIO_ANALYZER_SERVER_PORT`: port used by `python main.py`

Targeted config overrides use the `AUDIO_ANALYZER__...` prefix.

Example:

```bash
AUDIO_ANALYZER__MODELS__ASR__DEVICE=GPU python main.py
```

## Key Sections

- `models.asr`: backend provider, model name, device, export precision, decoding settings
- `audio_preprocessing`: chunk size, silence detection, denoise settings, chunk directory
- `audio_util`: max file size, allowed extensions, upload read chunk size
- `pipeline.delete_chunks_after_use`: whether temporary chunks are removed after processing
- `sentiment`: enablement, provider, model, device, aggregation settings

## Common Values

- `models.asr.provider`: `openai` | `openvino` | `whispercpp`
- `models.asr.device`: `CPU` | `GPU` | `NPU`
- `models.asr.weight_format`: OpenVINO export precision such as `int8`, `fp16`, or `null`; for `whispercpp`, quantization such as `q5`, `q5_0`, `q5_1`, `q8`, `q8_0`, `int5`, `int8`, or `null`
- `sentiment.enabled`: `true` or `false`
- `sentiment.provider`: `openvino` or `pytorch`
- `sentiment.weight_format`: optional OpenVINO export precision such as `int8`, `fp16`, or `null`

## ASR Provider Notes

- `openai`: uses `openai-whisper` and downloads PyTorch Whisper weights on first use.
- `openvino`: exports the configured Whisper model to OpenVINO IR under `models/openvino/...` and supports `CPU`, `GPU`, and `NPU` (when available and correctly configured).
- `whispercpp`: downloads the matching whisper.cpp `ggml` model under `models/whispercpp/...` and runs on `CPU` only.

### ASR Provider/Device Matrix

- `openai`: `CPU` only
- `whispercpp`: `CPU` only
- `openvino`: `CPU` | `GPU` | `NPU`

If an invalid provider/device combination is configured, startup fails with a clear validation error.

### OpenVINO NPU Configuration

Use this config structure:

```yaml
models:
  asr:
    provider: openvino
    device: NPU
```

For Docker Compose, ensure:

- `ACCEL_MOUNT_PATH` points to the host NPU node (host path is machine-specific; for example `/dev/accel/accel0` on many Meteor Lake systems)
- `ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so` remains set in the container environment

Path mapping semantics:

- Host path (configurable): `ACCEL_MOUNT_PATH=<host device node>`
- Container path (fixed): `/dev/accel/accel0`

Compose mapping in `docker-compose.yml`:

```yaml
devices:
  - ${ACCEL_MOUNT_PATH:-/dev/null}:/dev/accel/accel0
```

This keeps CPU/GPU usage independent of NPU availability:

- If `ACCEL_MOUNT_PATH` is set, Compose maps that host device into `/dev/accel/accel0`.
- If `ACCEL_MOUNT_PATH` is not set, Compose maps `/dev/null` to `/dev/accel/accel0` so CPU/GPU workflows still run without a host NPU device.

Verify host node availability and resolved mapping:

```bash
ls -l /dev/accel/
docker compose config
```

Validation performed by the service at startup:

1. Requested provider/device from config is valid.
2. Requested OpenVINO device is visible in `ov.Core().available_devices` inside the running environment.
3. OpenVINO can compile a probe model on the requested device.
4. For `NPU`, initialization of the NPU compiler/runtime stack succeeds.

Provider-specific `models.asr` fields:

- `weight_format`: used by `openvino` for IR export precision and by `whispercpp` for model quantization.
- `beam_size`, `best_of`, `threads`, `word_timestamps`: used only by `whispercpp`.
