<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Testing — VLM OpenVINO Serving

## Run

```bash
poetry install --with test
cd tests && poetry run pytest                    # config: tests/pytest.ini
poetry run pytest test_app.py -k streaming -x    # subset
poetry run coverage run --source=src -m pytest && poetry run coverage report
```

`tests/pytest.ini` sets `testpaths = .` — run pytest **from `tests/`** (or
pass explicit paths) so config and filterwarnings apply.
`pyproject.toml` sets `asyncio_default_fixture_loop_scope = module` for
`pytest-asyncio`.

## The import-time trap (why unmocked tests hang or download models)

`src/app.py` executes `initialize_model()` **at module import**. Any test file
importing `src.app` must first patch the environment and the loaders —
`tests/test_app.py` does this at module level, before the import:

```python
with mock.patch.dict(os.environ, {..., "VLM_MODEL_NAME": "mock_model"}):
    with mock.patch("src.utils.utils.convert_model", return_value=None):
        with mock.patch("openvino_genai.VLMPipeline", return_value=mock.Mock()):
            with mock.patch("src.utils.utils.is_model_ready", return_value=True):
                with mock.patch("src.app.initialize_model"):
                    from src.app import app   # only now is the import safe
```

Symptoms of getting this wrong: pytest "hangs" during collection, network
downloads from huggingface.co, or `RuntimeError: Error initializing the
model`. Fix: mock **before** import, never after.

## What the suite covers (`tests/`)

| File | Coverage |
|---|---|
| `test_app.py` | ~50 tests: health/device/models routes, per-model chat flows (qwen / phi / smolvlm / default), streaming, queue status, GPU-OOM restart path |
| `test_utils.py` | conversion, image/video loading, device helpers |
| `test_common.py` | Settings parsing, error strings |
| `test_data_models.py` | request/response schema validation |

## Adding a test for a new endpoint or model branch

1. Reuse the module-level mock stack from `test_app.py` (import once, reuse
   its `TestClient`).
2. For a new model family, patch the pipeline/processor the branch uses and
   assert on the prompt construction, not the mocked output.
3. Keep tests offline: any code path that would touch huggingface.co or
   OpenVINO device enumeration must be patched
   (`src.utils.utils.get_devices`, `is_model_ready`, `convert_model`).
4. Gate coverage locally with the `coverage` commands above before pushing.
