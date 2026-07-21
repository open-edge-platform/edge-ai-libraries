<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Source map — VLM OpenVINO Serving

## `src/app.py` — the whole service (~1600 lines)

| Area | Symbols | Notes |
|---|---|---|
| App + lifecycle | `lifespan()`, `app = FastAPI(...)`, CORS middleware | lifespan only starts a request-count logger; the heavy init is import-time |
| **Model init (import time!)** | `initialize_model()` (~line 460) — **called at module level** right after its definition | sets globals `pipe`, `processor`, `model_dir`, `model_config`, `model_ready`; SmolVLM → `OVModelForVisualCausalLM` (optimum-intel) + `AutoProcessor`, everything else → `openvino_genai.VLMPipeline` |
| Chat route | `@app.post("/v1/chat/completions")` → `chat_completions()` (~line 627) | per-model prompt branches: Qwen (`qwen_vl_utils.process_vision_info`, video kwargs), Phi (ChatML + `<|image_i|>` markers), SmolVLM (HF chat template), default |
| Generation | `run_generation()`, `safe_generate()`, `launch_streaming_generation()`, `create_streaming_response()`, `collect_streamer_output()` | non-stream = `asyncio.to_thread(pipe.generate, ...)`; stream = background `Thread` + queue streamer feeding SSE |
| OOM recovery | `restart_server()` (~line 408), `cleanup_pipeline_state()` | on GPU OOM (`error code: -5`) the process re-execs itself via `os.execv` |
| Observability | `/v1/telemetry` → `list_telemetry()`, `/v1/queue-status`, `log_telemetry()` | telemetry persisted through `src/utils/telemetry_store.py` (file-locked JSONL) |
| Introspection | `/v1/models`, `/device`, `/device/{device}`, `/health` | device info via `ov.Core()` helpers in `src/utils/utils.py` |

## `src/utils/`

| File | Contents |
|---|---|
| `common.py` | `Settings` (pydantic-settings; env vars), `ErrorMessages` (incl. `GPU_OOM_ERROR_MESSAGE = "error code: -5"`), `ModelNames` — the **substring dispatch constants** (`qwen2`, `phi-3.5-vision`, `smolvlm`), logger |
| `utils.py` | `convert_model()` (optimum export), `load_images()` (async, proxy-aware), `get_devices()`/`get_device_property()`, `is_model_ready()`, `load_model_config()`, qwen tensor helpers, `decode_and_save_video()`, `validate_video_inputs()`, `setup_seed()` |
| `data_models.py` | Pydantic schemas: `ChatRequest`, `Message` + content union (`MessageContentText/ImageUrl/Video/VideoUrl`), responses, telemetry models |
| `telemetry.py` / `telemetry_store.py` | build usage+telemetry from openvino_genai `PerfMetrics`; JSONL ring buffer shared across workers |

## Config & scripts

- `src/config/model_config.yaml` — per-model `min_pixels`/`max_pixels` (Qwen
  processors) and the `video_supported_models` substring list.
- `scripts/compress_model.sh` — container-start model export:
  `optimum-cli export openvino --trust-remote-code --weight-format <fmt>` into
  `ov-model/<model-basename>/<fmt>`; skips if present; special-cases
  MiniCPM-o (`--task image-text-to-text`).
- `docker/Dockerfile` — two-stage python:3.12-slim, Poetry with
  `virtualenvs.create false`, non-root `appuser` (uid 1000), `EXPOSE 8000`;
  GPU drivers via `scripts/install_ubuntu_gpu_drivers.sh`
  (`INSTALL_DRIVER_VERSION` build arg).

## Adding a model family (checklist)

1. Add a dispatch constant in `src/utils/common.py` (`ModelNames`) — matching
   is by substring of the lowercased model name.
2. Add the prompt/processing branch in `chat_completions()` in `src/app.py`
   (and in `initialize_model()` if it needs a non-`VLMPipeline` loader).
3. Add pixel limits / video support to `src/config/model_config.yaml`.
4. Mock-test it in `tests/test_app.py` (copy an existing per-model test class).
5. Update `docs/user-guide/Overview.md` supported-models table.
