# OVMS/OpenVINO model layout in VSS

This document mirrors the actual model repository under:

`config/ovms_config/models/`

The canonical VLM example is:

`Qwen_Qwen2.5-VL-3B-Instruct_CPU_int8/`

The top-level OVMS config used by compose is:

`config/ovms_config/models/config.json`

`docker/compose.summary.yaml` mounts `../config/ovms_config:/workspace:ro` and starts OVMS with `--config_path workspace/models/config.json`.

## Naming convention

`setup.sh` computes storage model names so multiple device/precision variants can coexist.

- Normal source model: sanitize non `[A-Za-z0-9_.-]` characters to `_`, then append `_DEVICE_precision`.
- Example: `Qwen/Qwen2.5-VL-3B-Instruct`, `CPU`, `int8` -> `Qwen_Qwen2.5-VL-3B-Instruct_CPU_int8`.
- `OpenVINO/*` namespace sources are treated as pre-converted and append only `_DEVICE`.

The active Qwen directory name is therefore part of the API-facing model identity used by pipeline-manager through `VLM_STORAGE_MODEL_NAME` and `LLM_STORAGE_MODEL_NAME`.

## Top-level OVMS config

`config/ovms_config/models/config.json` currently contains:

```json
{
  "model_config_list": [
    {
      "config": {
        "name": "Qwen_Qwen2.5-VL-3B-Instruct_CPU_int8",
        "base_path": "Qwen_Qwen2.5-VL-3B-Instruct_CPU_int8"
      }
    }
  ]
}
```

For a new OVMS model, add one `model_config_list` entry where:

- `name` is the storage model name clients will call.
- `base_path` is the directory under `config/ovms_config/models`, relative to the config file directory.

`setup.sh` can reset stale entries at runtime and will add the models required for the selected VLM/LLM split mode.

## Qwen directory file map

Files present in the real Qwen example:

```text
added_tokens.json
chat_template.jinja
config.json
generation_config.json
graph.pbtxt
merges.txt
openvino_config.json
openvino_detokenizer.bin
openvino_detokenizer.xml
openvino_language_model.bin
openvino_language_model.xml
openvino_text_embeddings_model.bin
openvino_text_embeddings_model.xml
openvino_tokenizer.bin
openvino_tokenizer.xml
openvino_vision_embeddings_merger_model.bin
openvino_vision_embeddings_merger_model.xml
openvino_vision_embeddings_model.bin
openvino_vision_embeddings_model.xml
preprocessor_config.json
special_tokens_map.json
tokenizer_config.json
tokenizer.json
video_preprocessor_config.json
vocab.json
```

### `graph.pbtxt`

The Qwen graph is an OVMS MediaPipe graph with:

- `input_stream: "HTTP_REQUEST_PAYLOAD:input"`
- `output_stream: "HTTP_RESPONSE_PAYLOAD:output"`
- `calculator: "HttpLLMCalculator"`
- `pipeline_type: VLM_CB`
- `models_path: "./"`
- `enable_prefix_caching: true`
- `cache_size: 10`
- `max_num_seqs: 256`
- `device: "CPU"`

Why it matters: this is the serving graph OVMS loads for `/v3` OpenAI-compatible chat/completion calls. Change `pipeline_type`, `device`, `cache_size`, and plugin config only to match the exported model and target hardware. For an LLM-only summarizer use the exporter defaults or omit VLM-specific pipeline type. For VLM captioning, keep `VLM_CB` when using the continuous batching VLM path.

### Converted OpenVINO IR files

Qwen has these IR pairs:

- `openvino_language_model.xml/.bin`: main autoregressive language model. The XML exposes inputs such as `attention_mask`, `position_ids`, `inputs_embeds`, and `beam_idx`; the BIN contains weights.
- `openvino_text_embeddings_model.xml/.bin`: token embedding model. Qwen's XML has an `input` parameter of token ids and int8 embedding weights.
- `openvino_vision_embeddings_model.xml/.bin`: visual patch/encoder entry model. Qwen's XML begins with image/video hidden-state-style parameters.
- `openvino_vision_embeddings_merger_model.xml/.bin`: Qwen-specific visual feature merger/projection stage. Keep this only if your converted architecture produces this file; other VLM families may use different projection filenames.
- `openvino_tokenizer.xml/.bin`: OpenVINO tokenizer accepting string input.
- `openvino_detokenizer.xml/.bin`: OpenVINO detokenizer mapping generated token ids back to text.

Why they matter: OVMS loads these exact files by convention through the LLM/VLM calculator. Do not create fake XML/BIN files. If a conversion exports different component names, inspect the exporter output and adapt the directory/graph to what OVMS supports for that architecture.

### Model and generation metadata

- `config.json`: architecture metadata from Transformers. Qwen declares `Qwen2_5_VLForConditionalGeneration`, `model_type: qwen2_5_vl`, text settings, vision settings, and token ids such as image/video/vision markers. Replace with the new model's actual config.
- `openvino_config.json`: export and quantization metadata. Qwen records `dtype: int8`, `optimum_version`, `transformers_version`, and quantization config using `Qwen/Qwen2.5-VL-3B-Instruct` as processor/tokenizer. Replace by real export output.
- `generation_config.json`: default generation behavior. Qwen uses `do_sample: true`, EOS/PAD ids, `repetition_penalty: 1.05`, and near-zero `temperature`. Adjust to the new tokenizer and desired behavior.

### Prompt/template and tokenizer files

- `chat_template.jinja`: Jinja chat prompt used to serialize messages. Qwen inserts `<|vision_start|><|image_pad|><|vision_end|>` for images and `<|vision_start|><|video_pad|><|vision_end|>` for videos. Replace with the new model's real chat template.
- `tokenizer.json`: full tokenizer graph/vocabulary.
- `tokenizer_config.json`: tokenizer options and special-token decoder.
- `special_tokens_map.json`: maps EOS/PAD/additional special tokens.
- `added_tokens.json`: Qwen's added token ids for `<|im_start|>`, `<|im_end|>`, `<|image_pad|>`, `<|video_pad|>`, etc.
- `vocab.json` and `merges.txt`: BPE vocabulary and merges used by Qwen.

Why they matter: token ids in these files must align with `config.json`, `generation_config.json`, `chat_template.jinja`, and tokenizer/detokenizer IR. Mixing files from Qwen with a different model commonly causes bad prompts, wrong EOS handling, or tokenizer failures.

### Preprocessor files

- `preprocessor_config.json`: image preprocessing. Qwen uses `Qwen2VLImageProcessorFast`, `processor_class: Qwen2_5_VLProcessor`, `patch_size: 14`, `merge_size: 2`, `temporal_patch_size: 2`, and min/max pixel limits.
- `video_preprocessor_config.json`: video preprocessing. Qwen uses `Qwen2VLVideoProcessor`, `min_frames: 4`, `max_frames: 768`, and the same image normalization/rescale settings.

Why they matter: VSS captioning sends video/image content to the VLM path. Frame sampling, patch size, pixel limits, normalization, and RGB conversion must match the vision encoder.

## Conversion path in this repo

`setup.sh` exports `OVMS_CONFIG_DIR="${PWD}/config/ovms_config"` and uses `export_model_for_ovms()` for OVMS VLM/LLM models. That function:

1. Computes a storage name with `get_ovms_storage_model_name()`.
2. Computes a KV cache size for CPU/GPU unless `OVMS_CACHE_SIZE_GB` overrides it.
3. Downloads OVMS `export_model.py` from the `v2026.1` tag.
4. Creates `config/ovms_config/ovms_venv`.
5. Installs either minimal dependencies for `OpenVINO/*` pre-converted models or the OVMS export requirements.
6. Optionally authenticates to Hugging Face if `GATED_MODEL=true` and `HUGGINGFACE_TOKEN` is set.
7. Runs `python3 export_model.py text_generation ... --model_repository_path models --config_file_path models/config.json --target_device <device> --cache_size <gb>`.

The checked-in `config/ovms_config/export_model.py` shows the conversion command for non-OpenVINO sources:

```bash
optimum-cli export openvino --model <source> --weight-format <precision> --trust-remote-code <destination>
```

If the exported model lacks tokenizer/detokenizer IR, the exporter runs:

```bash
convert_tokenizer --with-detokenizer --trust-remote-code -o <destination> <source>
```

For embedding models, the same exporter has an `embeddings_ov` subcommand that runs feature-extraction export plus tokenizer conversion and creates an embedding `graph.pbtxt`. Note: the VSS search path normally uses `multimodal-embedding-serving`/SDK variables rather than the OVMS VLM config.

## Deployment wiring

### OVMS summary/captioning

`docker/compose.summary.yaml` defines `ovms-service`:

- image: `openvino/model_server:2026.1`
- mount: `../config/ovms_config:/workspace:ro`
- command includes `--config_path workspace/models/config.json`
- REST port maps to `${OVMS_HTTP_HOST_PORT}:80`, default from setup is `8300`.
- gRPC port maps to `${OVMS_GRPC_HOST_PORT}:81`, default from setup is `9300`.

`pipeline-manager` receives:

- `LLM_SUMMARIZATION_API=${LLM_SUMMARIZATION_API}`
- `VLM_CAPTIONING_API=${VLM_ENDPOINT}`
- `LLM_MODEL_NAME=${LLM_STORAGE_MODEL_NAME:-${LLM_MODEL_NAME}}`
- `VLM_MODEL_NAME=${VLM_STORAGE_MODEL_NAME:-${VLM_MODEL_NAME}}`

In OVMS mode, `setup.sh` sets both APIs to `http://ovms-service/v3`.

### GPU OVMS

`docker/compose.gpu_ovms.yaml` changes `ovms-service` to `openvino/model_server:2026.1-gpu` and passes `/dev/dri` plus `/dev/accel/accel0` when available. `setup.sh` adds this compose file when either `VLM_TARGET_DEVICE` or `LLM_TARGET_DEVICE` contains `GPU`. Default weight format becomes `int4` for GPU/NPU unless overridden.

### vLLM bypass

`docker/compose.vllm.yaml` is separate from OVMS. It starts `vllm-cpu-service` with:

```yaml
--model ${VLM_MODEL_NAME}
--dtype ${VLLM_DTYPE:-bfloat16}
--trust-remote-code
```

When `ENABLE_VLLM=true`, `setup.sh` uses `VLLM_ENDPOINT` for both VLM captioning and LLM summarization and ignores separate OVMS LLM model selection.

### Search embedding path

`docker/compose.search.yaml` wires search embeddings through `multimodal-embedding-serving` and/or SDK mode:

- `MULTIMODAL_EMBEDDING_MODEL` for search/dual frame embeddings.
- `TEXT_EMBEDDING_MODEL` for unified summary-search text embeddings.
- `EMBEDDING_PROCESSING_MODE=sdk` by default.
- `OV_MODELS_DIR`/`EMBEDDING_OV_MODELS_DIR` default to `/app/ov_models` inside containers, backed by the `ov-models` volume.

So, adding an embedding model for VSS search is usually not the same as registering the Qwen-style VLM directory in OVMS. Use the OVMS `embeddings_ov` path only if the caller explicitly wants an OVMS embeddings endpoint and then wire the client endpoint/model name accordingly.

## Safe onboarding checklist

1. Inspect the converter output directory before editing config.
2. Verify every XML has a matching BIN where applicable.
3. Replace Qwen metadata with the new model's real `config.json`, tokenizer files, chat template, and preprocessors.
4. Keep `graph.pbtxt` `models_path: "./"` when artifacts are directly in the model directory.
5. Register exactly the storage name in `models/config.json`.
6. Run `source setup.sh --summary config` to confirm model names and compose wiring.
7. Start with `source setup.sh --summary` and check OVMS readiness plus container logs.
