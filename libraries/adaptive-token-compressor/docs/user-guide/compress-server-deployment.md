# Compress Server Deployment

The Compress Server is the FastAPI service that serves model-based text
compression to HarnessCompressor and ContextCompressor. Two deployment options
are available:

- [Docker Compose Deployment](#docker-compose-deployment-recommended)
  (recommended)
- [Bare-Metal Installation](#bare-metal-installation), for hosts where Docker
  is not available

## Docker Compose Deployment (Recommended)

Reference docker compose recipe for the Compress Server. The PyTorch service
uses **XPU** by default. Select the runtime by starting the corresponding
service; use `COMPRESS_SERVER_DEVICE` to choose the hardware.

The deployment uses two runtime-specific Dockerfiles:

- `Dockerfile.pytorch` for PyTorch / IPEX / XPU
- `Dockerfile.ov` for OpenVINO

These are alternative runtimes. Start only the server that matches your
requirements; you do not need to run both services.

The compose file defines two services:

- `compress-server-pytorch` on host port `8001`
- `compress-server-ov` on host port `8002`

### Quick start

```bash
cd deployment/compress-server
docker compose up -d --build compress-server-pytorch
```

Default: `--device xpu`, `--port 8001`. The library client default
(`TokenPruneBackend(compress_server_url="http://localhost:8001/compress")`)
matches out of the box — no config change required.

To start the OpenVINO service:

```bash
docker compose up -d --build compress-server-ov
```

Default: `--device gpu`, `--port 8002`. Point the client at
`http://localhost:8002/compress` to use it.

### Override variables (no .env file needed)

All variables have `:-default` fallbacks in `docker-compose.yaml`. Pass
inline on the command line:

```bash
# CPU fallback
COMPRESS_SERVER_DEVICE=cpu docker compose up -d --build compress-server-pytorch

# OpenVINO runtime (devices: cpu / gpu, lowercase; default gpu)
COMPRESS_SERVER_DEVICE=cpu docker compose up -d --build compress-server-ov

# Select device index (PyTorch xpu:<index>; OpenVINO GPU.<index>). CPU takes no index.
COMPRESS_SERVER_DEVICE=xpu COMPRESS_SERVER_DEVICE_INDEX=1 docker compose up -d --build compress-server-pytorch

# Different port
COMPRESS_SERVER_PORT=9000 docker compose up -d --build compress-server-pytorch

# Combine
COMPRESS_SERVER_DEVICE=cpu COMPRESS_SERVER_PORT=9000 docker compose up -d --build compress-server-pytorch
```

| Variable | Default | Notes |
| ---------- | --------- | ------- |
| `COMPRESS_SERVER_BIND_HOST` | `127.0.0.1` | Host bind address for the published port. Setting it to `0.0.0.0` exposes the HTTP service to the network and is generally not recommended without appropriate network and TLS controls. |
| `COMPRESS_SERVER_PORT` | `8001` | Container always listens on `8001`; this maps host port. |
| `COMPRESS_SERVER_OV_PORT` | `8002` | Host port for the `compress-server-ov` service. |
| `COMPRESS_SERVER_DEVICE` | `xpu` (pytorch) / `gpu` (ov) | Lowercase, case-insensitive. Shared by both services: pytorch accepts `cpu` / `xpu`; ov accepts `cpu` / `gpu`. ov defaults to `gpu`. `xpu`/`gpu` require `/dev/dri`. Don't pass pytorch-only `xpu` to the ov profile. |
| `COMPRESS_SERVER_DEVICE_INDEX` | `0` | Index within the device class. PyTorch uses `xpu:<index>`; OpenVINO uses `GPU.<index>` (falls back to generic `GPU` for index `0`). Ignored/rejected for `cpu`. |
| `COMPRESS_SERVER_MODE` | `llmlingua2` | Compression mode: `llmlingua2` only. |
| `COMPRESS_SERVER_MODEL_NAME_ID` | (empty) | HF model ID. If empty, defaults to `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank`. |
| `HF_HUB_OFFLINE` | `0` | First-run downloads allowed. Set `1` for strict offline. Default is `0` because the image ships no model — a fresh machine must pull it on first start. Once the model is cached (and, for OV, the IR is persisted), prefer `HF_HUB_OFFLINE=1`: with `0`, hf_hub still issues metadata/revalidation calls on every start, `1` trusts the local cache and makes zero network calls, so it is faster. |
| `HF_ENDPOINT` | `https://hf-mirror.com` | Mainland China mirror; unset/override for upstream HF. |
| `http_proxy`/`https_proxy`/`no_proxy` | (unset) | Build-time + runtime proxies. |
| `VIDEO_GID`/`RENDER_GID` | `44`/`992` | GPU passthrough; detect on host with `getent group`. |

### Verify

```bash
curl http://localhost:8001/health
# → {
#     "status":"ok",
#     "mode":"llmlingua2",
#     "supports_request_mode_override":true,
#     "supported_modes":["llmlingua2"],
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

For the OpenVINO service use host port `8002` (or your `COMPRESS_SERVER_OV_PORT`)
instead of `8001`. Its `/health` reports the OV device, e.g.
`"device":"ov:GPU","execution_devices":"GPU (Intel(R) Arc(TM) B390 GPU (iGPU))"`.

For OV runtime, the startup logs include explicit device mapping and resolved
runtime info, e.g.:

- `Runtime=ov  Requested device=GPU` (or `CPU`; ov normalizes to uppercase internally)
- `OpenVINO requested device=GPU mapped device=GPU.0` (or `GPU` fallback for index `0`)
- `OV[GPU.0] name: Intel(R) ...` (device name may vary by runtime)
- `OpenVINO execution devices (startup probe): GPU (Intel(R) ...)` (device name may vary by runtime)
- `Model runtime device: ov:GPU.0` (or `ov:GPU`)

Test that the `digit_neighbor_radius` patch is active:

```bash
curl -X POST http://localhost:8001/compress \
  -H 'Content-Type: application/json' \
  -d '{"text":"price is 99.5 USD nearby","rate":0.3,"force_reserve_digit":true,"digit_neighbor_radius":3}'
# → {"compressed_prompt":"price is 99. 5 USD nearby","compressed_prompt_list":["price is 99. 5 USD nearby"],"origin_tokens":8,"compressed_tokens":9,"ratio":"0.9x","rate":"112.5%","saving":", Saving $-0.0 in GPT-4.","compression_time_ms":285.33,"compression_time_s":0.285}
```

### Stop & cleanup

```bash
docker compose --profile pytorch down  # stop / remove the PyTorch service/container
docker compose --profile ov down       # stop / remove the OpenVINO service/container
docker compose --profile pytorch --profile ov down -v  # remove both services and the HF model cache volume
```

## Bare-Metal Installation

Alternative to the recommended Docker Compose deployment above, for hosts
where Docker is not available. Runs the same server without Docker, from the
`adaptive-token-compressor` package. Pick **one** extra per virtualenv,
matching the runtime you launch with (`--runtime pytorch|ov`). The package is
installed from source, so run the `pip install` commands below from the
repository root.

### Install (PyTorch runtime — XPU)

```bash
pip install --extra-index-url https://download.pytorch.org/whl/xpu \
            --extra-index-url https://pytorch-extension.intel.com/release-whl/stable/xpu/us/ \
            ".[compress-server-pytorch-xpu]"
```

### Install (PyTorch runtime — CPU)

For CPU-only hosts, use the lighter `compress-server-pytorch-cpu` extra (no IPEX / XPU wheels):

```bash
pip install --index-url https://download.pytorch.org/whl/cpu \
            --extra-index-url https://pypi.org/simple \
            ".[compress-server-pytorch-cpu]"
```

### Install (OpenVINO runtime — cpu / gpu)

```bash
pip install --index-url https://download.pytorch.org/whl/cpu \
            --extra-index-url https://pypi.org/simple \
            ".[compress-server-ov]"
```

### Apply the neighbor-protection patch (one-time, required)

The neighbor-protection patch modifies LLMLingua-2's source to enable the
`digit_neighbor_radius` request field. After installing an extra, run once:

```bash
python -m adaptive_token_compressor.model_servers.compress_server.apply_patch
```

Diagnostic / CI check (no apply):

```bash
python -m adaptive_token_compressor.model_servers.compress_server.apply_patch --check
echo $?    # 0 = patched, 1 = not patched
```

### Run

```bash
python -m adaptive_token_compressor.model_servers.compress_server    # default --runtime pytorch --device xpu --port 8001
python -m adaptive_token_compressor.model_servers.compress_server --runtime pytorch --device cpu
python -m adaptive_token_compressor.model_servers.compress_server --runtime ov            # ov default device: gpu
python -m adaptive_token_compressor.model_servers.compress_server --runtime ov --device cpu
python -m adaptive_token_compressor.model_servers.compress_server --model_name_id microsoft/llmlingua-2-xlm-roberta-large-meetingbank
```

The server binds `localhost` by default (`--host`). Every flag also reads the
`COMPRESS_SERVER_*` variable of the same name (e.g. `COMPRESS_SERVER_DEVICE`,
`COMPRESS_SERVER_PORT`, `COMPRESS_SERVER_MODEL_NAME_ID`); the `/health` and
`/compress` checks in the [Verify](#verify) section above apply unchanged.

Models are downloaded from the HuggingFace Hub on first use; the endpoint defaults
to the `https://hf-mirror.com` mirror — pass `--hf_endpoint` or set
`HF_ENDPOINT=https://huggingface.co` for upstream.

### Compatible client

```python
from adaptive_token_compressor.core.backends import TokenPruneBackend

backend = TokenPruneBackend(compress_server_url="http://localhost:8001/compress", timeout=60.0)
result = backend.compress(
    text="...",
    rate=0.6,
    force_reserve_digit=True,
    digit_neighbor_radius=3,
)
```

## See also

- Library usage and configuration: [get-started.md](./get-started.md)
- Companion vLLM tool predictor: [tool-predictor-deployment.md](./tool-predictor-deployment.md)
