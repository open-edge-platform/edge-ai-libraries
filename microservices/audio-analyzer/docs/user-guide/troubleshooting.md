# Troubleshooting

## Service Will Not Start

- Confirm port `8010` is not already in use:

  ```bash
  ss -ltnp | grep 8010
  ```

- Confirm the active config file is valid YAML. The service loads
  `config.yaml`, then applies `AUDIO_ANALYZER__...` environment overrides.
  The same `config.yaml` is used by both standalone and container runs
  (bind-mounted into the container).

## First Startup Is Slow

This is expected. On first run the service may download or export model
assets to `models/` and the Hugging Face cache. Subsequent starts reuse the
cached artifacts.

## `health` Endpoint Fails

- For Docker: check `docker compose ps` and
  `docker compose logs -f audio-analyzer`.
- For standalone: confirm the process is running and bound to the expected
  host/port (defaults `127.0.0.1:8010`).
- If you are behind a corporate proxy, pass `--noproxy '*'` to `curl` when
  hitting `127.0.0.1`.

## GPU Path Is Not Used

- The OpenVINO `GPU` device requires the Intel/OpenVINO host GPU runtime
  installed on the host (separate from the Python dependencies).
- For the container, `/dev/dri` must be exposed to the container (default in
  `docker-compose.yml`).
- **Docker vs host `.venv`:** The Docker Compose environment is the verified
  configuration for GPU and NPU acceleration. Running directly with the host
  `.venv` may report only `CPU` in `openvino.Core().available_devices` if the
  host Intel GPU/NPU runtime stack is not fully installed. In that case, startup
  fails fast with a message such as:

  ```text
  RuntimeError: Configured OpenVINO ASR device 'GPU' is not visible in this runtime.
  OpenVINO available_devices=['CPU'].
  ```

  This is a host runtime environment limitation, not an application bug. Use the
  Docker Compose flow (`docker compose up -d --build`) for GPU and NPU
  acceleration; the container image includes the necessary OpenVINO GPU and NPU
  runtime libraries and exposes `/dev/dri` by default.

## NPU Path Is Not Used

- Confirm the host exposes the NPU device node you intend to map. On Meteor
  Lake systems this is commonly `/dev/accel/accel0`.
- Set `ACCEL_MOUNT_PATH` to that host device node for Compose runs.
- `ACCEL_MOUNT_PATH` is the host-side path; Compose maps it to the fixed
  container path `/dev/accel/accel0`.
- Keep `ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so` in the container environment.
- Make sure the container runs with the host render group via `RENDER_GID` so
  the app user can access the Intel NPU device node.
- If `core.available_devices` still reports only `CPU`, re-check that you are
  using the NPU-capable image built from the updated Dockerfile and that the
  host Intel NPU driver stack is installed and loaded.

Recommended verification sequence:

1. Verify host NPU node:

  ```bash
  ls -l /dev/accel/
  ```

2. Verify resolved Compose device mapping:

  ```bash
  docker compose config
  ```

  Under `services.audio-analyzer.devices`, confirm:

  - with `ACCEL_MOUNT_PATH` set:
    - `source: <your host NPU path>`
    - `target: /dev/accel/accel0`
  - without `ACCEL_MOUNT_PATH` set:
    - `source: /dev/null`
    - `target: /dev/accel/accel0`

3. Verify container sees the mapped NPU node:

  ```bash
  docker compose exec audio-analyzer ls -l /dev/accel/
  ```

4. Verify OpenVINO runtime sees NPU inside the container:

  ```bash
  docker compose exec audio-analyzer python3 -c "import openvino as ov; print([str(d).upper() for d in ov.Core().available_devices])"
  ```

5. Verify startup validation passes and service is healthy:

  ```bash
  docker compose logs -f audio-analyzer
  curl --noproxy '*' http://127.0.0.1:8010/health
  ```

The service validates requested ASR provider/device at startup and fails fast
when a configured device is unsupported or not visible in OpenVINO.

When `device: NPU` is configured but NPU is not available, startup fails with a
runtime validation error similar to:

```text
RuntimeError: Configured OpenVINO ASR device 'NPU' is not visible in this runtime.
OpenVINO available_devices=['CPU', 'GPU'].
For NPU, ensure ACCEL_MOUNT_PATH maps the host NPU node into /dev/accel/accel0
and ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so is set.
```

## whisper-large Rejected at Startup on NPU

If startup fails with an error like:

```text
RuntimeError: Model 'whisper-large' with device=NPU is not supported on this NPU hardware
(confirmed ZE_RESULT_ERROR_UNINITIALIZED at pfnAppendGraphExecute on Intel Core Ultra
NPU architecture 3720 with OpenVINO 2026.1). ...
```

this is a **confirmed NPU driver/firmware limitation**, not an Audio Analyzer bug.

**Root cause:** whisper-large (1.55 B parameters, 32 decoder layers, ~5.9 GB FP32 weights) fails
at the Level Zero `pfnAppendGraphExecute` API during inference on Intel Core Ultra "AI Boost" NPU
(architecture 3720). The NPU driver compiles the model successfully — startup takes ~200 s — but
cannot execute the resulting graph at inference time. The Level Zero error code is
`ZE_RESULT_ERROR_UNINITIALIZED (0x78000001)`. OpenVINO reports "no fallback possible".

This was verified with:

- **Hardware:** Intel Core Ultra (Meteor Lake), NPU Intel(R) AI Boost, architecture 3720
- **OpenVINO:** 2026.1.0-21367-63e31528c62
- **OpenVINO-GenAI:** 2026.1.0.0-2957-1dabb8c2255
- **NPU compiler type:** DRIVER (driver-integrated compiler, version 524289)
- **Standalone reproduction:** `ov_genai.WhisperPipeline` loads successfully but `pipe.generate()` raises `RuntimeError` on the first inference call

**Validated pass:** whisper-tiny, whisper-base, whisper-small, and whisper-medium all complete
NPU inference successfully on the same hardware with the same driver.

**Workaround:** Use `device: CPU` or `device: GPU` for whisper-large. Both pass
full inference validation.

**If a future NPU driver update resolves this:** remove `"whisper-large"` from
`_OPENVINO_NPU_INFERENCE_UNSUPPORTED` in `utils/openvino_runtime_validation.py`
and rerun the full validation matrix:

```bash
# Minimal standalone repro to confirm whether a driver update fixes the issue
docker run --rm --user 1000:1000 --group-add <RENDER_GID> \
  --device /dev/dri:/dev/dri \
  --device <ACCEL_MOUNT_PATH>:/dev/accel/accel0 \
  -e ZE_ENABLE_ALT_DRIVERS=libze_intel_npu.so \
  -v audio-analyzer_audio_analyzer_models:/app/audio_analyzer/models \
  intel/audio-analyzer:<VERSION> \
  python3 -c "
import numpy as np, openvino_genai as ov_genai
pipe = ov_genai.WhisperPipeline('/app/audio_analyzer/models/openvino/whisper-large', device='NPU')
r = pipe.generate(np.zeros(16000*3, dtype='float32'), return_timestamps=True)
print('PASS:', r.texts[0])
"
```

## Invalid ASR Provider/Device Combination

If startup fails with an error about `models.asr.provider` or
`models.asr.device`, ensure your config matches the supported matrix:

- `openai`: `CPU` only
- `whispercpp`: `CPU` only
- `openvino`: `CPU` | `GPU` | `NPU`

Example supported NPU configuration:

```yaml
models:
  asr:
    provider: openvino
    device: NPU
```

When switching devices, restart the service/container and confirm logs.

## Permission Errors on Mounted Folders

The container runs as UID/GID `1000:1000` (baked into the image).
Model, chunk, storage, and Hugging Face cache data are kept in named
Docker volumes (`audio_analyzer_{models,chunks,storage,cache}`)
initialized with that ownership, so this rarely fails on a fresh
install. If you do see:

```text
PermissionError: [Errno 13] Permission denied: '/app/audio_analyzer/storage/...'
```

you are most likely reusing volumes that were initialized by a previous
run as a different UID (for example by an older root-only run). Reset
them:

```bash
docker compose down
docker volume rm \
  audio-analyzer_audio_analyzer_models \
  audio-analyzer_audio_analyzer_chunks \
  audio-analyzer_audio_analyzer_storage \
  audio-analyzer_audio_analyzer_cache
docker compose up -d
```

## Microphone / `GET /devices` Returns Empty

- Confirm ALSA capture devices exist on the host:

  ```bash
  arecord -l
  ```

- For the container, uncomment the `/dev/snd` device mapping in
  `docker-compose.yml`.

## FFmpeg or `libsndfile` Errors (Standalone)

Install the required host packages:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg alsa-utils libsndfile1
```

## Sessions / Transcripts Not Persisting

Session files live under `storage/<session_id>/`. Confirm that directory is
writable by the process and is on a persistent volume in container
deployments.

## Supporting Resources

- [Configuration Guide](./get-started/configuration.md)
- [API Reference](./api-reference.md)
- [System Requirements](./get-started/system-requirements.md)
