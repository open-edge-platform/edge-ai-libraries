<!--
SPDX-FileCopyrightText: (C) 2026 Intel Corporation
SPDX-License-Identifier: Apache-2.0
-->

# Source map — Multimodal Embedding Serving

## Request flow

```
src/app.py            routes + Pydantic input union; @app.on_event("startup")
                      loads the model via the factory; globals embedding_model,
                      health_status
  └─ src/wrapper.py   EmbeddingModel — embed_query / embed_documents /
                      get_image_embedding_from_url|base64 /
                      get_video_embedding(s)_from_* / check_health /
                      modality helpers.  ← SDK surface too
      └─ src/models/registry.py   ModelFactory + MODEL_HANDLER_REGISTRY,
                                  get_model_handler(), register_model_handler(),
                                  is_model_supported()
          └─ src/models/handlers/<family>_handler.py
                                  load_model / encode_text / encode_image;
                                  PyTorch path + optional OpenVINO path
```

## Key modules

| Path | Contents |
|---|---|
| `src/models/config.py` | `MODEL_CONFIGS` — the 19-model registry; `get_model_config()` injects device/OV/batch settings from env; `list_available_models()` |
| `src/models/base.py` | `BaseEmbeddingModel` ABC: abstract `load_model`/`encode_text`/`encode_image`/`convert_to_openvino`; capability hooks `supports_text/image/video`; instruction hooks `prepare_query/documents`; `get_embedding_dim` (default 512) |
| `src/models/handlers/` | `clip_handler.py` (reference implementation: open_clip PyTorch path + `optimum.intel.OVModelOpenCLIPVisual/Text` OV path), `cn_clip_handler.py`, `mobileclip_handler.py`, `siglip_handler.py`, `blip2_handler.py`, `blip2_transformers_handler.py`, `qwen_handler.py` (text-only, `OVModelForFeatureExtraction`, instruction template + last-token pooling) |
| `src/models/utils/openvino_utils.py` | `check_and_convert_openvino_models()`, `load_openvino_models()`, `AsyncBatchInference` (AsyncInferQueue streaming) |
| `src/utils/common.py` | pydantic `Settings` (note: falls back to `_env_file=None` for SDK use), `ErrorMessages`, logger |
| `src/utils/utils.py` | `download_image/video`, `decode_base64_*`, `validate_remote_media_url` (SSRF checks), `ParallelImagePreprocessor`, proxy bypass |
| `src/utils/decoder.py` | `extract_batched_frames` — shared-memory-pool video frame pipeline |
| `src/utils/path_security.py` | filename/extension allowlists; sandbox root `/tmp/videoQnA` for `video_file`/`frames_batch` |

## Adding a model family (checklist)

1. Create `src/models/handlers/<family>_handler.py` subclassing
   `BaseEmbeddingModel`; implement `load_model`, `encode_text`,
   `encode_image` (and OV conversion if supported). Copy `clip_handler.py`
   as the template.
2. Register the handler class in `MODEL_HANDLER_REGISTRY`
   (`src/models/registry.py`).
3. Add entries to `MODEL_CONFIGS` in `src/models/config.py` (model id
   `Family/name`, weights source, dim, handler class name, capabilities).
4. If the family needs new pip deps: add to `pyproject.toml` if on PyPI;
   otherwise install in `docker/Dockerfile` (like mobileclip) and document
   that the family is container-only.
5. Update `setup.sh`'s known-model `case` (it warns on unknown ids) and
   `docs/user-guide/supported-models.md`.
6. Smoke-test: `GET /models` lists it, `GET /model/capabilities` is right,
   one `POST /embeddings` per supported modality.

## Config & scripts

- `docker/Dockerfile` — two-stage python:3.12-slim; pip-installs
  `git+…ml-mobileclip` and `salesforce-lavis==1.0.2 --no-deps`; single-worker
  gunicorn CMD with `--timeout 300 --log-level debug`.
- `setup.sh` — env defaults, model-name validation, volume creation, GPU →
  OV auto-enable.
- `logging.conf` — logger configuration loaded by the app.
