# Lingua Server — Docker Compose Deployment

Reference docker compose recipe for the Lingua FastAPI server.
Default backend is **PyTorch** on **XPU**. You can switch backend with
`LINGUA_BACKEND` and keep hardware selection via `LINGUA_DEVICE`.

The deployment now uses two backend-specific Dockerfiles:

- `Dockerfile.pytorch` for PyTorch / IPEX / XPU
- `Dockerfile.ov` for OpenVINO

The compose file now defines two services:

- `lingua-pytorch` on host port `8001`
- `lingua-ov` on host port `8002` (opt-in via profile; override with `LINGUA_OV_PORT`)

One server instance supports both compression modes (`llmlingua2` and
`longllmlingua`). `LINGUA_MODE` sets only the startup default; request payload
`mode` can override it per `/compress` call.

Each image carries only the standalone server file and its runtime deps.
The PyTorch image installs torch + IPEX + llmlingua + fastapi + uvicorn.
The OpenVINO image installs CPU torch + OpenVINO + optimum[openvino].
Neither image installs the `adaptive-token-compressor` library — clients reach
the running container over HTTP via `LinguaHTTPBackend(lingua_url=...)`.

## Quick start

```bash
cd deployment/lingua
docker compose up -d --build lingua-pytorch
```

Default: `--device xpu`, `--port 8001`. The library client default
(`LinguaHTTPBackend(lingua_url="http://localhost:8001/compress")`)
matches out of the box — no config change required.

To start the OpenVINO service:

```bash
docker compose --profile ov up -d --build lingua-ov
```

Explicit startup examples:

```bash
# PyTorch / IPEX / XPU
docker compose up -d --build lingua-pytorch

# OpenVINO / XPU
docker compose --profile ov up -d --build lingua-ov
```

Current backend/mode support status:

- PyTorch + `llmlingua2`: supported
- PyTorch + `longllmlingua`: supported
- OpenVINO + `llmlingua2`: supported
- OpenVINO + `longllmlingua`: not supported with the current implementation

Default startup mode: `llmlingua2`.

## Override variables (no .env file needed)

All variables have `:-default` fallbacks in `docker-compose.yaml`. Pass
inline on the command line:

```bash
# CPU fallback
LINGUA_DEVICE=cpu docker compose up -d --build lingua-pytorch

# OpenVINO backend on XPU (maps to OV GPU)
LINGUA_DEVICE=xpu docker compose --profile ov up -d --build lingua-ov

# Select XPU index (PyTorch xpu:<index>; OpenVINO prefers GPU.<index>)
LINGUA_DEVICE=xpu LINGUA_XPU_INDEX=1 docker compose up -d --build lingua-pytorch

# Different port
LINGUA_PORT=9000 docker compose up -d --build lingua-pytorch

# Pin mode + model independently
LINGUA_MODE=llmlingua2 \
LINGUA_MODEL_NAME_ID=microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank \
  docker compose up -d --build lingua-pytorch

# LongLLMLingua mode with separate model id
LINGUA_MODE=longllmlingua \
LINGUA_MODEL_NAME_ID=NousResearch/Llama-2-7b-hf \
    docker compose up -d --build lingua-pytorch

# Combine
LINGUA_DEVICE=cpu LINGUA_PORT=9000 docker compose up -d --build lingua-pytorch
```

Use `longllmlingua` only with the PyTorch service. The current OpenVINO path
supports `llmlingua2` but does not support `longllmlingua`.

| Variable | Default | Notes |
|---|---|---|
| `LINGUA_PORT` | `8001` | Container always listens on `8001`; this maps host port. |
| `LINGUA_OV_PORT` | `8002` | Host port for the `lingua-ov` service. |
| `LINGUA_BACKEND` | `pytorch` | Kept for the server process; compose service selection uses `lingua-pytorch` / `lingua-ov`. |
| `LINGUA_DEVICE` | `xpu` | `xpu` / `cpu` / `cuda`. xpu requires `/dev/dri` on host. |
| `LINGUA_XPU_INDEX` | `0` | XPU index when `LINGUA_DEVICE=xpu`. PyTorch uses `xpu:<index>`; OpenVINO prefers `GPU.<index>` and accepts generic `GPU` as fallback for index `0`. |
| `LINGUA_MODE` | `llmlingua2` | Compression mode: `llmlingua2` or `longllmlingua`. |
| `LINGUA_MODEL_NAME_ID` | (empty) | HF model ID. If empty, defaults are mode-specific: `llmlingua2` → `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`, `longllmlingua` → `NousResearch/Llama-2-7b-hf`. |
| `HF_HUB_OFFLINE` | `0` | First-run downloads allowed. Set `1` for strict offline. |
| `HF_ENDPOINT` | `https://hf-mirror.com` | Mainland China mirror; unset/override for upstream HF. |
| `http_proxy`/`https_proxy`/`no_proxy` | (unset) | Build-time + runtime proxies. |
| `VIDEO_GID`/`RENDER_GID` | `44`/`992` | GPU passthrough; detect on host with `getent group`. |

## Verify

```bash
curl http://localhost:8001/health
# → {
#     "status":"ok",
#     "mode":"llmlingua2",
#     "supports_request_mode_override":true,
#     "supported_modes":["llmlingua2","longllmlingua"],
#     "initialized_modes":{
#       "llmlingua2":{
#         "model_name_id":"...",
#         "device":"xpu:0",
#         "execution_devices":"n/a"
#       }
#     }
#   }

curl -X POST http://localhost:8001/compress \
  -H 'Content-Type: application/json' \
  -d '{"text":"...","rate":0.5}'
# → {"compressed_prompt":"...","compression_time_ms":12.3,...}
```

For OV backend, the startup logs include explicit device mapping and resolved
runtime info, e.g.:

- `Backend=ov  Requested device=xpu`
- `OpenVINO requested device=xpu mapped device=GPU.0` (or `GPU` fallback for index `0`)
- `OV[GPU.0] name: Intel(R) ...` (device name may vary by runtime)
- `OpenVINO execution devices: ['GPU']` / `GPU.0` (runtime-specific)
- `Model runtime device: ov:GPU.0` (or `ov:GPU`)

Test the `digit_neighbor_radius` patch is active:

```bash
curl -X POST http://localhost:8001/compress \
  -H 'Content-Type: application/json' \
  -d '{"text":"price is 99.5 USD nearby","rate":0.3,"force_reserve_digit":true,"digit_neighbor_radius":3}'
# → compressed_prompt should retain "99.5" and surrounding words
```

## Stop & cleanup

```bash
docker compose down                # stop / remove the default service/container
docker compose --profile ov down   # stop / remove the OpenVINO service/container
docker compose down -v             # also remove HF model cache volume
```

## See also

- Bare-metal install (without docker): `src/adaptive_token_compressor/model_servers/lingua/README.md`
  uses `pip install adaptive-token-compressor[lingua-server[-cpu]]` +
  `python -m adaptive_token_compressor.model_servers.lingua.apply_patch` +
  `python -m adaptive_token_compressor.model_servers.lingua`
- Companion vLLM tool predictor: `deployment/tool_predictor/README.md`
