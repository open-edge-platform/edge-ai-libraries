---
name: vss-model-onboarding
description: Guides developers through onboarding models for the video-search-and-summarization sample app, grounded in its actual OVMS/OpenVINO model repository layout. Use when a user wants to use a different VLM, swap the summarization model, add my own embedding model, convert a model to OpenVINO for OVMS, or register a new model in OVMS for the video-search-and-summarization sample app.
---

# VSS model onboarding

Use this skill to bring a new VLM/LLM, or an OVMS-hosted embedding model, into the VSS sample without inventing paths. The canonical example in this repo is:

`config/ovms_config/models/Qwen_Qwen2.5-VL-3B-Instruct_CPU_int8/`

For an annotated file-by-file map, see [references/ovms-model-layout.md](references/ovms-model-layout.md). A starter helper lives at [scripts/prepare_ovms_model.py](scripts/prepare_ovms_model.py).

## 1. Identify the target and storage name

1. Choose the source model id/path, target device, and precision.
2. Use this repo's storage naming convention:
   - Hugging Face style source: sanitize `/` to `_`, then append device and precision.
   - Example: `Qwen/Qwen2.5-VL-3B-Instruct` + `CPU` + `int8` becomes `Qwen_Qwen2.5-VL-3B-Instruct_CPU_int8`.
   - OpenVINO namespace models append device only in `setup.sh`.
3. For VSS summarization/captioning, set `VLM_MODEL_NAME` and optionally `OVMS_LLM_MODEL_NAME`, `VLM_TARGET_DEVICE`, `LLM_TARGET_DEVICE`, and compression format overrides.

## 2. Convert/export the model

Preferred repo path is the OVMS exporter used by `setup.sh`:

```bash
cd config/ovms_config
python3 export_model.py text_generation \
  --source_model <hf-id-or-local-model> \
  --model_name <storage-model-name> \
  --weight-format int8 \
  --config_file_path models/config.json \
  --model_repository_path models \
  --target_device CPU \
  --pipeline_type VLM_CB
```

`setup.sh` automates this by downloading OVMS `export_model.py`, installing the OVMS export requirements, running `optimum-cli export openvino --trust-remote-code`, converting tokenizer/detokenizer when needed, creating `graph.pbtxt`, and updating `models/config.json`.

For a starter scaffold before conversion:

```bash
python3 skills/vss-model-onboarding/scripts/prepare_ovms_model.py \
  --source-model <hf-id-or-local-model> \
  --model-name <storage-model-name> \
  --device CPU \
  --precision int8
```

Then replace copied template metadata and `.PENDING` placeholders with artifacts from the real conversion.

## 3. Build the model directory like the Qwen example

A VLM directory must contain the files OVMS and the model runtime expect:

- `graph.pbtxt`: MediaPipe graph for `HttpLLMCalculator`; Qwen uses `pipeline_type: VLM_CB`, `models_path: "./"`, `device: "CPU"`, and cache/concurrency settings.
- `openvino_language_model.xml/.bin`: converted language model IR and weights.
- `openvino_text_embeddings_model.xml/.bin`: token embedding IR and weights.
- `openvino_vision_embeddings_model.xml/.bin`: visual encoder IR and weights.
- `openvino_vision_embeddings_merger_model.xml/.bin`: Qwen-specific vision merger IR and weights; only keep if the new architecture exports it.
- `openvino_tokenizer.xml/.bin` and `openvino_detokenizer.xml/.bin`: OpenVINO tokenizer and detokenizer used by OVMS serving.
- `config.json`, `openvino_config.json`, `generation_config.json`: architecture, quantization/export metadata, and generation defaults.
- `preprocessor_config.json`, `video_preprocessor_config.json`: image/video preprocessing. These are architecture-specific; do not blindly reuse Qwen values.
- `chat_template.jinja`, tokenizer files (`tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`, `added_tokens.json`, `vocab.json`, `merges.txt`): prompt formatting and token vocabulary.

## 4. Register the model in OVMS

The active OVMS config is `config/ovms_config/models/config.json` and currently registers Qwen with:

```json
{"config": {"name": "Qwen_Qwen2.5-VL-3B-Instruct_CPU_int8", "base_path": "Qwen_Qwen2.5-VL-3B-Instruct_CPU_int8"}}
```

Add your storage model name with `base_path` equal to the directory name relative to `config/ovms_config/models`. Avoid stale entries; `setup.sh` may reset this file to the models required for the current run.

## 5. Wire deployment

- OVMS compose mounts `../config/ovms_config` as `/workspace` and starts with `--config_path workspace/models/config.json`.
- CPU OVMS uses `docker/compose.summary.yaml`; GPU adds `docker/compose.gpu_ovms.yaml` and image `openvino/model_server:2026.1-gpu`.
- OVMS endpoints exposed to pipeline-manager are `http://ovms-service/v3` for both `LLM_SUMMARIZATION_API` and `VLM_CAPTIONING_API`.
- The pipeline-manager calls `VLM_STORAGE_MODEL_NAME` and `LLM_STORAGE_MODEL_NAME`, not necessarily the raw HF names.
- vLLM mode (`ENABLE_VLLM=true`) bypasses OVMS and uses `docker/compose.vllm.yaml` with `--model ${VLM_MODEL_NAME}`.

## 6. Validate

1. Run `source setup.sh --summary config` to inspect resolved compose and names without starting containers.
2. Run `source setup.sh --summary` to start OVMS-backed summary mode.
3. Check OVMS readiness at `http://localhost:${OVMS_HTTP_HOST_PORT:-8300}/v2/health/ready`.
4. If search embeddings are being changed, remember VSS search normally uses `multimodal-embedding-serving`/SDK variables (`MULTIMODAL_EMBEDDING_MODEL`, `TEXT_EMBEDDING_MODEL`, `OV_MODELS_DIR`), not the OVMS VLM config.
