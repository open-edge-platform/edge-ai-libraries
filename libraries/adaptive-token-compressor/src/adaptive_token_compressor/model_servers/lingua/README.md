# Lingua Server

Wraps Microsoft LLMLingua-2 as a FastAPI HTTP service. Compatible with
`LinguaHTTPBackend` in `adaptive_token_compressor.core.backends`.

## Install (XPU — default)

```bash
pip install --extra-index-url https://download.pytorch.org/whl/xpu \
            --extra-index-url https://pytorch-extension.intel.com/release-whl/stable/xpu/us/ \
            "adaptive-token-compressor[lingua-server]"
```

This installs `torch==2.8.0` + `torchvision==0.23.0` + `torchaudio==2.8.0` from
PyTorch XPU index, plus `intel-extension-for-pytorch==2.8.10+xpu` +
`oneccl_bind_pt==2.8.0+xpu` from Intel index, plus llmlingua + fastapi + uvicorn.

## Install (CPU fallback)

```bash
pip install "adaptive-token-compressor[lingua-server-cpu]"
```

No IPEX, no XPU wheels — default PyPI index works. Pass `--device cpu` on launch.

## Apply LLMLingua-2 source patch (one-time, required)

After installing extras, run once:

```bash
python -m adaptive_token_compressor.model_servers.lingua.apply_patch
```

This patches LLMLingua-2's `prompt_compressor.py` in your site-packages
to enable the `digit_neighbor_radius` field. Idempotent — re-running is
safe (detects existing patch via marker string and skips).

Diagnostic / CI check (no apply):

```bash
python -m adaptive_token_compressor.model_servers.lingua.apply_patch --check
echo $?    # 0 = patched, 1 = not patched
```

If you skip the patch, `force_reserve_digit=True` still works at radius 0;
the `digit_neighbor_radius` field is silently ignored.

## Run

```bash
python -m adaptive_token_compressor.model_servers.lingua    # default --backend pytorch --device xpu --port 8001
python -m adaptive_token_compressor.model_servers.lingua --backend pytorch --device cpu
python -m adaptive_token_compressor.model_servers.lingua --backend ov --device xpu
python -m adaptive_token_compressor.model_servers.lingua --backend ov --device cpu
python -m adaptive_token_compressor.model_servers.lingua --model_name microsoft/llmlingua-2-xlm-roberta-large-meetingbank
```

## Models

- `microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank` (default — faster)
- `microsoft/llmlingua-2-xlm-roberta-large-meetingbank` (better quality, slower)

Models are downloaded from HuggingFace Hub on first use. Set
`HF_ENDPOINT=https://hf-mirror.com` for users in mainland China.

## API

### `POST /compress`

```json
{
  "text": "...",
  "rate": 0.6,
  "force_tokens": ["\\n", "?"],
  "force_reserve_digit": true,
  "digit_neighbor_radius": 3
}
```

Returns:

```json
{"compressed_prompt": "...", "compression_time_ms": 123.4, "..."}
```

### `GET /health`

```json
{"status": "ok", "device": "xpu:0", "tensor_device": "xpu:0"}
```

For OV backend, health looks like:

```json
{"status": "ok", "device": "ov:GPU", "tensor_device": "cpu"}
```

## LLMLingua-2 source patch — what it does

`force_reserve_digit` is native to LLMLingua-2 (keeps digit-containing
words). `digit_neighbor_radius` is **not** native — it teaches
`PromptCompressor._main_compressor` to also keep the N words around each
digit-containing word.

The patch file (`patches/0001-digit-neighbor-radius.patch`) ships with this
package and is the single source of truth — the same file is used by both
the bare-metal `apply_patch` CLI (above) and the Docker builds under
`deployment/lingua/Dockerfile.pytorch` and `deployment/lingua/Dockerfile.ov`.

## Compatible client

```python
from adaptive_token_compressor.core.backends import LinguaHTTPBackend

backend = LinguaHTTPBackend(lingua_url="http://localhost:8001/compress", timeout=60.0)
result = backend.compress(
    text="...",
    rate=0.6,
    force_reserve_digit=True,
    digit_neighbor_radius=3,
)
```

## See also

- Docker compose deployment (recommended for production):
  `deployment/lingua/README.md` —
  `cd deployment/lingua && docker compose up -d --build` runs the same
  server inside a container without installing extras locally.

