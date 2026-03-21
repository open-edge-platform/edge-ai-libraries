# Pytest Notes (Internal)

> Internal-only test notes for maintainers. Do not expose this as user-facing documentation.

**Work folder:** `edge-ai-libraries/microservices/multilevel-video-understanding`

## 1) Environment setup (Poetry style, no fixed venv path)

Use steps aligned with [docs/user-guide/get-started.md](../docs/user-guide/get-started.md) -> `Manual Host Setup using Poetry`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install poetry==1.8.3
poetry lock --no-update
poetry install
# Install video-chunking-utils from OEP/EAL source
pip install ../../libraries/video-chunking-utils/
```

## 2) Test strategy

- Default mode: **mock-based API tests** under `tests/test_api`.
  - No external VLM/LLM serving dependency.
  - Fast and stable for CI.
- Optional mode: **external-serving integration test** under `tests/test_integration`.
  - Requires real VLM/LLM endpoints.
  - Use for end-to-end validation.

## 3) Run tests

Run API tests (default):

```bash
source .venv/bin/activate
pytest -q tests/test_api
```

Run integration test with external serving (optional):

```bash
source .venv/bin/activate
export ENABLE_EXTERNAL_SERVING_TESTS=1
export VLM_BASE_URL="http://<model-serving-ip-address>:41091/v1"
export LLM_BASE_URL="http://<model-serving-ip-address>:41090/v1"
export VLM_MODEL_NAME=Qwen/Qwen2.5-VL-7B-Instruct
export LLM_MODEL_NAME=Qwen/Qwen3-32B-AWQ
pytest -q tests/test_integration/test_summary_external_serving.py
```

## 4) Notes

- Keep unit/API tests independent from network and external model serving whenever possible.
- Keep integration tests opt-in and environment-gated (`ENABLE_EXTERNAL_SERVING_TESTS=1`).
