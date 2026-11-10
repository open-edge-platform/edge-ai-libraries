# How to prepare models

The engine only loads models that are already prepared on local disk. **It never downloads or exports a model at runtime.** This guide lists what each model is for and which options it has, and gives one preparation procedure for all of them. Following it, you can prepare every model you need on a clean machine.

All local models live under one model root directory:

- Local run: `data-intelligence-engine/workspace/models`
- Compose deployment: `data-intelligence-engine/workspace/models` on the host, mounted at `/workspace/models` in the container
- Custom: set `ENGINE_MODEL_ROOT_PATH` to the model root. Point it at the parent directory, not at one model. If the model root is outside the container's workspace, also mount it into the container at the same path.

The engine derives each model's subdirectory under the root from its configured model ID; see [Models at a glance](#2-models-at-a-glance). If a model is not found under the root, the engine also looks in the directory named by `MODEL_PATH` and then in the running user's `~/models`.

## Contents

- [Prepare models with one script](#prepare-models-with-one-script)
- [1. Decide which models you need](#1-decide-which-models-you-need)
- [2. Models at a glance](#2-models-at-a-glance)
- [3. Before you start](#3-before-you-start)
- [4. Prepare each model](#4-prepare-each-model)
  - [4.1 GME: documents, images and audio transcripts](#41-gme-documents-images-and-audio-transcripts)
  - [4.2 BGE: optional text-only embedding](#42-bge-optional-text-only-embedding)
  - [4.3 bge-reranker-large: optional reranking](#43-bge-reranker-large-optional-reranking)
  - [4.4 PP-DocLayoutV3: PDF layout detection](#44-pp-doclayoutv3-pdf-layout-detection)
  - [4.5 ViCLIP: short videos](#45-viclip-short-videos)
  - [4.6 Whisper: speech recognition](#46-whisper-speech-recognition)
  - [4.7 Qwen3-VL-Reranker-2B: unified media reranking](#47-qwen3-vl-reranker-2b-unified-media-reranking)
- [5. Check that the models are ready](#5-check-that-the-models-are-ready)
- [6. What you do not need to prepare](#6-what-you-do-not-need-to-prepare)

## Prepare models with one script

`data-intelligence-engine/scripts/prepare-models.sh` runs the download and conversion
steps of [section 4](#4-prepare-each-model) for you, each in a throwaway engine
container. It needs Docker and a built engine image (see step 1 of
[Before you start](#3-before-you-start)). A model whose output is already in
place is skipped, so you can rerun it.

```bash
cd engine/scripts
./prepare-models.sh                                  # everything the multimodal how-to uses
./prepare-models.sh gme reranker                     # only some models
./prepare-models.sh --all --gme-precision int4
```

| Option | Values | Description |
|---|---|---|
| `MODEL...` | `gme`, `reranker`, `media-reranker`, `media-reranker-int8`, `layout`, `viclip-b`, `viclip-l`, `cosmos-224p`, `whisper`, `bge` | Models to prepare; default `gme reranker layout viclip-b whisper media-reranker-int8` |
| `--all` | — | Every model above |
| `--gme-precision` | `int8` (default), `int4`, `fp32` | GME precision |
| `--video-precision` | `fp16` (default), `fp32` | Video embedding precision |
| `HF_MODEL_DIR` (environment) | Directory; default `data-intelligence-engine/workspace/hf_models` | Original models |
| `OV_MODEL_DIR` (environment) | Directory; default `data-intelligence-engine/workspace/models` | Converted models, the engine's model root |
| `ENGINE_IMAGE` (environment) | Image; default `data-intelligence-engine:latest` | Image the tools run in |

`HF_ENDPOINT` and the proxy variables are passed to the containers. The rest of
this guide is the manual procedure the script follows.

## 1. Decide which models you need

Prepare the models for the content you process. For text documents only, one document embedding model is enough.

| Content | Models needed | Notes |
|---|---|---|
| Text documents (txt, md, docx, body text of PDFs with a text layer) | Document embedding: GME (default) or BGE | Required |
| Figures in PDFs (fused image+text vectors) | GME + PP-DocLayoutV3 | PP-DocLayoutV3 finds the figures. Without it, PDFs are processed as text only |
| Scanned PDFs (no text layer) | PP-DocLayoutV3 + document embedding | Layout regions are read with Tesseract OCR, which the image already includes |
| Images | GME | Shares the GME package with document embedding |
| Short videos (≤ 60 s) | ViCLIP-B (default), ViCLIP-L or Cosmos-224p | Eight sampled frames per clip; longer videos are stored but not embedded |
| Audio | Whisper + GME | Whisper transcribes; GME embeds the transcript |
| Reranking retrieval results (default) | Qwen3-VL-Reranker-2B | Optional. Used only when a request has `postprocess`; scores document text, figures, images, video and audio together; see [Text-to-media retrieval](../text-to-media-retrieval.md) |
| Reranking document text with a text-only model | bge-reranker-large | Optional. Used when a request selects it or `ENGINE_RERANK_MODEL_ID` points to it |

## 2. Models at a glance

| Model | Purpose | Backend (`embedding_backend`) | Default directory under the model root | Options | Size (approx.) |
|---|---|---|---|---|---|
| GME-Qwen2-VL-2B (OpenVINO package) | Embedding for documents, PDF figures, images and audio transcripts, 1536 dimensions | `local_openvino` (GME runtime) | `gme-Qwen2-VL-2B-Instruct-OV/` | Precision `int8` (default) / `int4` / `fp32` | 8.3 GB download; package 2.1 GB at int8, 1.3 GB at int4 |
| BGE (for example `BAAI/bge-small-en-v1.5`) | Text-only embedding instead of GME, 384 dimensions | `local_openvino` | `bge-small-en-v1.5/` (last part of the model ID) | `--weight-format` at conversion | A few hundred MB |
| bge-reranker-large | Reranking retrieval results | `local_openvino` or `remote_openai_compatible` | `BAAI/bge-reranker-large/` (keeps the vendor directory) | `--weight-format` at conversion; or a remote rerank service | 2.2 GB at fp32, about 0.6 GB at int8 |
| Qwen3-VL-Reranker-2B | Unified reranking across video, image and audio-transcript hits | `local_openvino` (fixed) | `Qwen3-VL-Reranker-2B-INT8-OV/` (serving default); FP16 export in `Qwen3-VL-Reranker-2B-OV/` | `--frames`, `--seq-bucket` at conversion | 4.2 GB download; FP16 package about 12 GB (three graphs), INT8 about half that |
| PP-DocLayoutV3 (ONNX) | PDF layout detection: figure positions, scanned-page regions | `local_openvino` (fixed) | `PP-DocLayoutV3/` | None | 250 MB |
| ViCLIP-B (default) | Short-video embedding, 512 dimensions | `local_openvino` | `viclip-b-fp16/` | `fp16` (default) / `fp32` | Depends on precision |
| ViCLIP-L | Short-video embedding, 768 dimensions | `local_openvino` | `viclip-l-fp16/` | `fp16` (default) / `fp32` | Depends on precision |
| Cosmos-224p (optional) | Short-video embedding, 256 dimensions | `local_openvino` | `cosmos-224p-fp16/` | `fp16` (default) / `fp32` | Depends on precision |
| Whisper `openai/whisper-small` | Speech recognition | `local_openvino` (fixed) | `whisper-small/` | `--weight-format` at conversion | About 1 GB |

**The backend and the model are set separately.** The backend (`embedding_backend`: `local_openvino` or `remote_openai_compatible`) only says where a model runs; the runtime is chosen from the model. The model itself is named by `embedding_model` (a prepared model ID, such as `viclip-b-fp16`) (the directory name under the model root). There are two places to set them:

- Engine-wide defaults: the `ENGINE_*_EMBEDDING_*` and related environment variables; see each model in section 4.
- One source: its `operator_options` when you create it, which override the defaults.

Every model has a `*_DEVICE` variable. Video embedding defaults to `CPU`; set `ENGINE_VIDEO_EMBEDDING_DEVICE=GPU.0` to use an Intel GPU. Compose runs document embedding and reranking on `GPU` by default; set them to `CPU` on a host without an Intel GPU. All variables are listed in [Configuration in the engine user guide](../user-guide.md#configuration).

## 3. Before you start

Run all commands below from the repository's `data-intelligence-engine/` directory, in the same terminal. The commands in section 4 use the two variables set here; set them again in a new terminal.

1. **Build the engine image.** See [Step 1: Deploy in Get Started](../get-start.md#step-1-deploy). The image already contains `huggingface-cli`, `optimum-cli`, PyTorch and OpenVINO, so preparing models needs only Docker, with no Python packages on the host. Every command below runs in a throwaway container and does not change the image. Commands that use the repository's conversion scripts mount the current directory read-only at `/engine` in the container.

2. **Set the two model directories.**

   ```bash
   export HF_MODEL_DIR=$PWD/workspace/hf_models   # original models: checkpoints downloaded from Hugging Face
   export OV_MODEL_DIR=$PWD/workspace/models      # OV models: the model root the engine reads
   mkdir -p "$HF_MODEL_DIR" "$OV_MODEL_DIR"
   [ "$(id -u)" = 1000 ] || sudo chown 1000:1000 "$HF_MODEL_DIR" "$OV_MODEL_DIR"
   ```

   - `OV_MODEL_DIR` must be the model root the engine reads. For Compose that is `data-intelligence-engine/workspace/models`. If you put it elsewhere, set `ENGINE_MODEL_ROOT_PATH` to it and mount it into the engine container.
   - `HF_MODEL_DIR` is only used during preparation. Delete it after all conversions to free disk space.
   - The preparation containers write files as UID 1000, like the engine container. If your host UID is not 1000, the last line hands both directories to UID 1000.

3. **Network.** The download commands pass the host's `HF_ENDPOINT`, `http_proxy`, `https_proxy` and `no_proxy` into the container; unset variables are ignored. If Hugging Face is unreachable, set a mirror first:

   ```bash
   export HF_ENDPOINT=https://hf-mirror.com
   ```

## 4. Prepare each model

### 4.1 GME: documents, images and audio transcripts

#### 1. Download the original model

```bash
docker run --rm -e HF_ENDPOINT -e http_proxy -e https_proxy -e no_proxy \
  -v "$HF_MODEL_DIR:/hf" --entrypoint huggingface-cli data-intelligence-engine:latest \
  download Alibaba-NLP/gme-Qwen2-VL-2B-Instruct \
  --include "*.json" "*.safetensors" "merges.txt" \
  --local-dir /hf/gme-Qwen2-VL-2B-Instruct
```

#### 2. Convert to OpenVINO

```bash
docker run --rm -e http_proxy -e https_proxy -e no_proxy -e ENGINE_WORKSPACE=/tmp \
  -v "$HF_MODEL_DIR:/hf:ro" -v "$OV_MODEL_DIR:/ov" -v "$PWD:/engine:ro" \
  --entrypoint sh data-intelligence-engine:latest -c '
    set -e
    # The conversion needs Transformers 5; it is installed in this throwaway container only
    pip install --user -q --no-warn-script-location "transformers==5.10.4"
    cd /engine && PYTHONPATH=src python scripts/export_gme_ov.py \
      --checkpoint /hf/gme-Qwen2-VL-2B-Instruct --precision int8 \
      --output-dir /ov/gme-Qwen2-VL-2B-Instruct-OV
  '
```

#### 3. Output directory and options

Output directory: `$OV_MODEL_DIR/gme-Qwen2-VL-2B-Instruct-OV/`, with `gme_openvino_config.json`, `gme_language_<precision>.xml/.bin`, `gme_visual_<precision>.xml/.bin`, and the tokenizer and processor files. If you already have a GME package, copy it into this directory and skip steps 1 and 2.

| Option | Values | Description |
|---|---|---|
| `--precision` (conversion) | `int8` (default), `int4`, `fp32` | int4 is fastest with slightly lower accuracy; fp32 is most accurate and slowest |
| `--output-dir` (conversion) | Directory | Refused if the directory already exists |
| `ENGINE_DOC_EMBEDDING_BACKEND` | `local_openvino` (default) | Backend for document embedding; a GME package runs on the GME runtime |
| `ENGINE_DOC_EMBEDDING_MODEL_ID` | `gme-Qwen2-VL-2B-Instruct-OV` (default) | Package directory name under the model root |
| `ENGINE_DOC_EMBEDDING_DEVICE` | `CPU` (default; `GPU` in Compose), `GPU` | Device for document embedding |
| `ENGINE_IMAGE_EMBEDDING_BACKEND` | `local_openvino` (default) | Backend for image embedding |
| `ENGINE_IMAGE_EMBEDDING_MODEL_ID` | `gme-Qwen2-VL-2B-Instruct-OV` (default) | Package directory name under the model root |
| `ENGINE_IMAGE_EMBEDDING_DEVICE` | `CPU` (default), `GPU` | On the same device as document embedding, both share one runtime |
| `operator_options.embedding_model` (image source) | A separately prepared GME package ID | Select a weight variant by model ID; `operator_options.precision` is rejected |
| `operator_options.max_image_tokens` (image source) | Integer; defaults to the package's `processor.max_image_tokens` | Visual-token cap per image; the largest latency factor |

### 4.2 BGE: optional text-only embedding

#### 1. Download the original model

```bash
docker run --rm -e HF_ENDPOINT -e http_proxy -e https_proxy -e no_proxy \
  -v "$HF_MODEL_DIR:/hf" --entrypoint huggingface-cli data-intelligence-engine:latest \
  download BAAI/bge-small-en-v1.5 \
  --include "*.json" "*.safetensors" "vocab.txt" \
  --local-dir /hf/bge-small-en-v1.5
```

#### 2. Convert to OpenVINO

```bash
docker run --rm -v "$HF_MODEL_DIR:/hf:ro" -v "$OV_MODEL_DIR:/ov" \
  --entrypoint optimum-cli data-intelligence-engine:latest \
  export openvino --model /hf/bge-small-en-v1.5 --task feature-extraction \
  /ov/bge-small-en-v1.5
```

#### 3. Output directory and options

Output directory: `$OV_MODEL_DIR/bge-small-en-v1.5/`, with `openvino_model.xml/.bin`, `openvino_tokenizer.xml/.bin`, the config and the tokenizer files.

| Option | Values | Description |
|---|---|---|
| `--weight-format` (conversion) | `fp32` when omitted; `fp16`, `int8` | Put it before the output directory argument |
| `ENGINE_DOC_EMBEDDING_BACKEND` | `local_openvino` (default) | Same backend for BGE; the runtime is chosen from the model |
| `ENGINE_DOC_EMBEDDING_MODEL_ID` | `BAAI/bge-small-en-v1.5` | Required for BGE; the last part is the directory name under the model root |
| `ENGINE_DOC_EMBEDDING_DEVICE` | `CPU` (default; `GPU` in Compose), `GPU` | Device |
| `operator_options.embedding_model` | Model ID (directory name under the model root) | Another text model for one source |

### 4.3 bge-reranker-large: optional reranking

#### 1. Download the original model

```bash
docker run --rm -e HF_ENDPOINT -e http_proxy -e https_proxy -e no_proxy \
  -v "$HF_MODEL_DIR:/hf" --entrypoint huggingface-cli data-intelligence-engine:latest \
  download BAAI/bge-reranker-large \
  --include "*.json" "*.safetensors" "sentencepiece.bpe.model" \
  --local-dir /hf/bge-reranker-large
```

#### 2. Convert to OpenVINO

```bash
docker run --rm -v "$HF_MODEL_DIR:/hf:ro" -v "$OV_MODEL_DIR:/ov" \
  --entrypoint optimum-cli data-intelligence-engine:latest \
  export openvino --model /hf/bge-reranker-large --task text-classification \
  /ov/BAAI/bge-reranker-large
```

#### 3. Output directory and options

Output directory: `$OV_MODEL_DIR/BAAI/bge-reranker-large/`, with `openvino_model.xml/.bin`, `openvino_tokenizer.xml/.bin`, the config and the tokenizer files.

| Option | Values | Description |
|---|---|---|
| `--weight-format` (conversion) | `fp32` when omitted; `fp16`, `int8` | Put it before the output directory argument. `int8` cuts the size from about 2.2 GB to about 0.6 GB |
| `ENGINE_RERANK_BACKEND` | `local_openvino` (default), `remote_openai_compatible` | `remote_openai_compatible` calls a remote rerank service and needs no local model |
| `ENGINE_RERANK_MODEL_ID` | `BAAI/bge-reranker-large` | Makes bge the default reranker instead of `Qwen3-VL-Reranker-2B-INT8-OV`; path under the model root, including the vendor directory |
| `ENGINE_RERANK_DEVICE` | `CPU` (default; `GPU` in Compose), `GPU` | Device |
| `ENGINE_RERANK_API_BASE` | URL | Used by `remote_openai_compatible` only |

### 4.4 PP-DocLayoutV3: PDF layout detection

#### 1. Download the original model

```bash
docker run --rm -e HF_ENDPOINT -e http_proxy -e https_proxy -e no_proxy \
  -v "$HF_MODEL_DIR:/hf" --entrypoint huggingface-cli data-intelligence-engine:latest \
  download PaddlePaddle/PP-DocLayoutV3_safetensors \
  --include "*.json" "*.safetensors" \
  --local-dir /hf/PP-DocLayoutV3_safetensors
```

#### 2. Convert to ONNX

```bash
docker run --rm -e http_proxy -e https_proxy -e no_proxy -e ENGINE_WORKSPACE=/tmp \
  -v "$HF_MODEL_DIR:/hf:ro" -v "$OV_MODEL_DIR:/ov" -v "$PWD:/engine:ro" \
  --entrypoint sh data-intelligence-engine:latest -c '
    set -e
    # The conversion needs Transformers 5; it is installed in this throwaway container only
    pip install --user -q --no-warn-script-location "transformers==5.10.4"
    cd /engine && PYTHONPATH=src python scripts/export_pp_doclayout_v3.py \
      --model-path /hf/PP-DocLayoutV3_safetensors --output-dir /ov/PP-DocLayoutV3
  '
```

#### 3. Output directory and options

Output directory: `$OV_MODEL_DIR/PP-DocLayoutV3/`, with `pp_doclayout_v3.onnx`, `id2label.json` and `preprocessor_config.json`.

| Option | Values | Description |
|---|---|---|
| `--model-path` (conversion) | Original model directory | Conversion input |
| `--output-dir` (conversion) | Directory | Conversion output; skipped if the ONNX file already exists |
| `ENGINE_LAYOUT_DEVICE` | `CPU` (default), `GPU` | Device |

### 4.5 ViCLIP: short videos

#### 1. Download the original model

Choose a model:

| Model | Checkpoint |
|---|---|
| ViCLIP-B (default) | `OpenGVLab/ViCLIP-B-16-hf` |
| ViCLIP-L | `OpenGVLab/ViCLIP-L-14-hf` |

Download only the checkpoint you need:

```bash
docker run --rm -e HF_ENDPOINT -e http_proxy -e https_proxy -e no_proxy \
  -v "$HF_MODEL_DIR:/hf" --entrypoint huggingface-cli data-intelligence-engine:latest \
  download OpenGVLab/ViCLIP-B-16-hf --local-dir /hf/viclip-b

docker run --rm -e HF_ENDPOINT -e http_proxy -e https_proxy -e no_proxy \
  -v "$HF_MODEL_DIR:/hf" --entrypoint huggingface-cli data-intelligence-engine:latest \
  download OpenGVLab/ViCLIP-L-14-hf --local-dir /hf/viclip-l
```

#### 2. Convert to OpenVINO

Conversion executes checkpoint Python; use trusted sources only.

```bash
docker run --rm -e http_proxy -e https_proxy -e no_proxy \
  -v "$HF_MODEL_DIR:/hf:ro" -v "$OV_MODEL_DIR:/ov" -v "$PWD:/engine:ro" \
  --entrypoint sh data-intelligence-engine:latest -c '
    set -e
    pip install --user -r /engine/scripts/requirements-viclip-export.txt
    python /engine/scripts/export_viclip_ov.py \
      --model viclip-b --checkpoint /hf/viclip-b \
      --output-dir /ov/viclip-b-fp16 --precision fp16 --trust-local-code
  '
```

For ViCLIP-L, change `viclip-b` to `viclip-l` in the command. Output must be new or empty. See [export_viclip_ov.py](../../../scripts/export_viclip_ov.py) for all options.

For optional Cosmos, run `./scripts/prepare-models.sh cosmos-224p` from the engine directory; it uses [export_cosmos_ov.py](../../../scripts/export_cosmos_ov.py).

#### 3. Output directory and options

Output: `$OV_MODEL_DIR/<model>-<precision>/`, containing `video_embedding.json`, video/text XML and BIN pairs, and tokenizer files. Select that directory name with `operator_options.embedding_model`, for example `cosmos-224p-fp16`; use a separate collection when changing models.

| Option | Values | Description |
|---|---|---|
| `--precision` (conversion) | `fp16` (default), `fp32` | Use a matching `-fp16` or `-fp32` output directory |
| `ENGINE_VIDEO_EMBEDDING_BACKEND` | `local_openvino` (default) | Backend |
| `ENGINE_VIDEO_EMBEDDING_MODEL_ID` | `viclip-b-fp16` (default) | The last part is the directory name under the model root.  |
| `ENGINE_VIDEO_EMBEDDING_DEVICE` | `CPU` (default), `GPU`, `AUTO:GPU,CPU` | Device |
| `operator_options.embedding_model` | Prepared package ID | Override the video model for one source |
| `operator_options.frames_per_clip` | `8` | Fixed by the video model |

### 4.6 Whisper: speech recognition

#### 1. Download the original model

```bash
docker run --rm -e HF_ENDPOINT -e http_proxy -e https_proxy -e no_proxy \
  -v "$HF_MODEL_DIR:/hf" --entrypoint huggingface-cli data-intelligence-engine:latest \
  download openai/whisper-small \
  --include "*.json" "*.safetensors" "merges.txt" \
  --local-dir /hf/whisper-small
```

#### 2. Convert to OpenVINO

```bash
docker run --rm -v "$HF_MODEL_DIR:/hf:ro" -v "$OV_MODEL_DIR:/ov" \
  --entrypoint optimum-cli data-intelligence-engine:latest \
  export openvino --model /hf/whisper-small \
  --task automatic-speech-recognition-with-past /ov/whisper-small
```

#### 3. Output directory and options

Output directory: `$OV_MODEL_DIR/whisper-small/`, with `openvino_encoder_model.xml/.bin`, `openvino_decoder_model.xml/.bin`, the config, and the processor and tokenizer files.

| Option | Values | Description |
|---|---|---|
| `--weight-format` (conversion) | `fp32` when omitted; `fp16`, `int8` | Put it before the output directory argument |
| `ENGINE_ASR_MODEL_ID` | `openai/whisper-small` (default) | The last part is the directory name under the model root |
| `ENGINE_ASR_DEVICE` | `CPU` (default), `GPU` | Device |
| `ENGINE_ASR_LANGUAGE` | `zh` (default), `en`, etc., empty string | Transcription language; an empty string detects it automatically |
| `ENGINE_ASR_ENABLED` | `true` (default), `false` | With `false`, nothing is transcribed and Whisper is not loaded |

### 4.7 Qwen3-VL-Reranker-2B: unified media reranking

One forward-only OpenVINO graph is exported per mode (`text`, `image`, `video`). The text mode scores audio transcripts. The FP16 export is quantized into the default INT8 weight-only serving package. See [Text-to-media retrieval](../text-to-media-retrieval.md) for how the reranker is used.

#### 1. Download the original model

```bash
docker run --rm -e HF_ENDPOINT -e http_proxy -e https_proxy -e no_proxy \
  -v "$HF_MODEL_DIR:/hf" --entrypoint huggingface-cli data-intelligence-engine:latest \
  download Qwen/Qwen3-VL-Reranker-2B \
  --include "*.json" "*.safetensors" "merges.txt" "*.jinja" "scripts/*" \
  --local-dir /hf/Qwen3-VL-Reranker-2B
```

#### 2. Convert to OpenVINO

Export all three modes in one container. Any media file works as the trace sample: visual inputs are normalized to a fixed grid and video pairs are padded to one sequence bucket, so the traced shapes do not depend on the sample. The commands below synthesize a small image and clip for that purpose.

```bash
docker run --rm -v "$HF_MODEL_DIR:/hf:ro" -v "$OV_MODEL_DIR:/ov" -v "$PWD:/engine:ro" \
  --entrypoint sh data-intelligence-engine:latest -c '
    set -e
    python - <<PY
import cv2, numpy as np
from PIL import Image
Image.new("RGB", (64, 64), (120, 80, 40)).save("/tmp/sample.png")
writer = cv2.VideoWriter("/tmp/sample.mp4", cv2.VideoWriter_fourcc(*"mp4v"), 5, (64, 64))
for i in range(12):
    writer.write(np.full((64, 64, 3), i * 20, np.uint8))
writer.release()
PY
    for mode in text image video; do
      sample=
      [ "$mode" = image ] && sample=/tmp/sample.png
      [ "$mode" = video ] && sample=/tmp/sample.mp4
      python /engine/scripts/export_qwen3_vl_reranker_ov.py \
        --source /hf/Qwen3-VL-Reranker-2B --output /ov/Qwen3-VL-Reranker-2B-OV \
        --mode "$mode" ${sample:+--sample "$sample"}
    done
  '
```

#### 3. Quantize to INT8 for default serving

INT8 halves the model size and is built from the FP16 package, which is left
untouched. This step is required for the default model ID:

```bash
docker run --rm -v "$OV_MODEL_DIR:/ov" -v "$PWD:/engine:ro" \
  --entrypoint python data-intelligence-engine:latest \
  /engine/scripts/quantize_qwen3_vl_reranker_int8.py \
  --src /ov/Qwen3-VL-Reranker-2B-OV --dst /ov/Qwen3-VL-Reranker-2B-INT8-OV
```

Per the frozen-pool comparison, image and audio quality is unchanged within noise while video loses part of the FP16 reranking gain. To retain that video gain, serve the FP16 package with `ENGINE_MEDIA_RERANK_MODEL_ID=Qwen/Qwen3-VL-Reranker-2B`.

#### 4. Output directory and options

Default serving directory: `$OV_MODEL_DIR/Qwen3-VL-Reranker-2B-INT8-OV/`, with `reranker_text.xml/.bin`, `reranker_image.xml/.bin`, `reranker_video.xml/.bin`, `export_shapes.json` and the processor files. The FP16 export has the same layout in `Qwen3-VL-Reranker-2B-OV/`.

| Option | Values | Description |
|---|---|---|
| `--frames` (conversion) | `8` (default) | Sampled frames per video; the runtime default `MEDIA_RERANK_VIDEO_MAX_FRAMES` must match |
| `--seq-bucket` (conversion) | `768` (default) | Fixed token length video pairs are padded to; one compiled graph for every video query |
| `--overwrite` (conversion) | Flag | Re-export a mode whose IR already exists |
| `--mode` (quantization) | `INT8_ASYM` (default), `INT8_SYM` | NNCF weight-compression mode, per-channel |
| `ENGINE_MEDIA_RERANK_BACKEND` | `local_openvino` (default) | Backend (only supported value) |
| `ENGINE_MEDIA_RERANK_MODEL_ID` | `Qwen3-VL-Reranker-2B-INT8-OV` (default) | Package directory under the model root; use `Qwen3-VL-Reranker-2B-OV` to serve the FP16 export |
| `ENGINE_MEDIA_RERANK_DEVICE` | `GPU` (default, PTL iGPU), `CPU` | Device |

Before serving, run the parity checker against the official checkpoint; see [Prepare the OpenVINO model](../text-to-media-retrieval.md#prepare-the-openvino-model).

## 5. Check that the models are ready

After preparation, `$OV_MODEL_DIR` looks like this:

```text
$OV_MODEL_DIR/
├── gme-Qwen2-VL-2B-Instruct-OV/       gme_openvino_config.json, gme_language_int8.xml/.bin, gme_visual_int8.xml/.bin, tokenizer files
├── BAAI/bge-reranker-large/           openvino_model.xml/.bin, tokenizer files
├── Qwen3-VL-Reranker-2B-OV/           reranker_{text,image,video}.xml/.bin, export_shapes.json, processor files (FP16 export)
├── Qwen3-VL-Reranker-2B-INT8-OV/      same layout, default weight-only INT8
├── PP-DocLayoutV3/                    pp_doclayout_v3.onnx, id2label.json, preprocessor_config.json
├── viclip-b-fp16/                    video_embedding.json, video_encoder.xml/.bin, text_encoder.xml/.bin, tokenizer assets
├── viclip-l-fp16/                    same package layout, 768 dimensions (optional)
├── viclip-b-fp32/                    same ViCLIP-B family, fp32 precision (optional)
├── viclip-l-fp32/                    same ViCLIP-L family, fp32 precision (optional)
└── whisper-small/                     openvino_encoder_model.xml/.bin, openvino_decoder_model.xml/.bin, config.json, processor files
```

Once the engine runs, the model discovery API shows which models it recognizes. `ready: true` means the files needed for inference are complete:

```bash
for t in embedding multimodal asr reranker; do
  echo "== $t"; curl -s "http://localhost:16022/v1/models/$t" | jq -c '.models[] | {name, ready}'
done
```

A model is actually loaded when a source is attached to a pool, so problems show up there, before anything is ingested. If a model has a problem, the attach request returns `503` with the reason:

| Error | Cause |
|---|---|
| `No prepared OpenVINO ... at ...` | `openvino_model.xml/.bin` or the tokenizer files are missing. Convert again and put the result at the reported path |
| `No exported GME OpenVINO package at ...` | No `gme_openvino_config.json` in the directory, or it is nested more than one level deep |
| `GME precision 'x' is incomplete ...` | The XML/BIN files of the requested precision are missing |
| `... ships [...] and its default_precision ... is not among them` | The GME package has several precisions and none is the default. Keep one precision's files only |
| `No multimodal model recognized at ...` | The directory is neither a prepared video package nor a GME package |
| Video manifest or artifact validation error | Check `video_embedding.json`, both root-level IR pairs and tokenizer assets; a source checkpoint alone is not a runtime package |
| `frames_per_clip=N does not match ...` | The source's frame count differs from the video package's fixed eight frames |

Each source records the model it uses in its `profile` when it is created; see it with `curl -s http://localhost:16022/v1/libraries/<library>/sources | jq '.[].profile'`. Moving a model directory or changing a default later does not change what existing sources record.

## 6. What you do not need to prepare

- **OCR**: Tesseract and its Chinese language data are already in the engine image.
- **Tokenizer vocabulary**: the `cl100k_base` vocabulary used to count chunk tokens is installed with LlamaIndex and normally needs no preparation. If your installation lacks it, build the cache on a machine with network access, copy it to the runtime host, and set the same `TIKTOKEN_CACHE_DIR` for the engine process:

  ```bash
  TIKTOKEN_CACHE_DIR=/path/to/tokenizer-cache \
    python -c 'import tiktoken; tiktoken.get_encoding("cl100k_base")'
  ```

  A missing or corrupt cache fails with a preparation error; the engine never fetches it.
- **Video captions**: provided by an external video-summary service; set `ENGINE_VIDEO_SUMMARY_BASE_URL`. Without it, captioning is skipped and embedding is unaffected.
- **OKF extraction**: uses an external LLM service; see the [OKF extractor](../../../tools/okf_extractor/README.md).
