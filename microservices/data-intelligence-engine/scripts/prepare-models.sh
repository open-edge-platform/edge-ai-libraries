#!/usr/bin/env bash
# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
#
# Download the engine's models from Hugging Face and convert them to OpenVINO
# (or ONNX), each in a throwaway engine container. The steps are the ones in
# data-intelligence-engine/docs/user-guide/how-to-guides/how-to-prepare-models.md. A model whose output
# is already in place is skipped, so the script can be rerun. Video packages
# are validated before skipping; incomplete or incompatible output is rejected.

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: prepare-models.sh [options] [MODEL...]

Models (default: gme reranker layout viclip-b whisper media-reranker-int8):
  gme             GME-Qwen2-VL-2B: documents, PDF figures, images, audio transcripts
  reranker        bge-reranker-large
  media-reranker  Qwen3-VL-Reranker-2B (FP16): unified video/image/audio-transcript reranking
  media-reranker-int8
                  INT8 weight-only variant of media-reranker, the package the
                  console serves by default (builds the FP16 export first if missing)
  layout          PP-DocLayoutV3: PDF figure detection and scanned PDFs
  viclip-b        ViCLIP-B-16: video embedding (default)
  viclip-l        ViCLIP-L-14: video embedding
  cosmos-224p     Cosmos-Embed1-224p: video embedding
  whisper         Whisper small: speech recognition
  bge             bge-small-en-v1.5: text-only alternative to GME

Options:
  --all                    Prepare every model above
  --gme-precision VALUE     int8 (default), int4 or fp32
  --video-precision VALUE   fp16 (default) or fp32 stored OpenVINO weights
  -h, --help               Show this help

Video output: $OV_MODEL_DIR/<model>-<precision> (for example viclip-b-fp16).
Video conversion executes checkpoint Python; use trusted sources only.

Environment:
  HF_MODEL_DIR   Original models (default: data-intelligence-engine/workspace/hf_models)
  OV_MODEL_DIR   Converted models, the engine's model root (default: data-intelligence-engine/workspace/models)
  ENGINE_IMAGE   Engine image to run the tools in (default: data-intelligence-engine:latest)
  HF_ENDPOINT, http_proxy, https_proxy, no_proxy are passed to the containers.
EOF
}

ENGINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${ENGINE_IMAGE:-data-intelligence-engine:latest}"
HF_MODEL_DIR="${HF_MODEL_DIR:-$ENGINE_DIR/workspace/hf_models}"
OV_MODEL_DIR="${OV_MODEL_DIR:-$ENGINE_DIR/workspace/models}"
# GME and PP-DocLayoutV3 conversion patch or use Transformers 5 internals; the
# engine image pins 4.x for optimum-intel, so 5.x goes into the throwaway
# container only. This is the version the GME export was validated with.
TRANSFORMERS5="transformers==5.10.4"
ALL_MODELS=(gme reranker media-reranker media-reranker-int8 layout viclip-b viclip-l cosmos-224p whisper bge)

gme_precision=int8
video_precision=fp16
models=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --all) models=("${ALL_MODELS[@]}") ;;
    --gme-precision) gme_precision="${2:?--gme-precision needs a value}"; shift ;;
    --video-precision) video_precision="${2:?--video-precision needs a value}"; shift ;;
    -h|--help) usage; exit 0 ;;
    -*) printf 'Unknown option: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
    *) models+=("$1") ;;
  esac
  shift
done
[[ ${#models[@]} -gt 0 ]] || models=(gme reranker layout viclip-b whisper media-reranker-int8)
case "$gme_precision" in int8|int4|fp32) ;; *) echo "--gme-precision must be int8, int4 or fp32" >&2; exit 2 ;; esac
case "$video_precision" in fp16|fp32) ;; *) echo "--video-precision must be fp16 or fp32" >&2; exit 2 ;; esac

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'error: %s\n' "$*" >&2; exit 1; }

# A throwaway engine container with both model directories and the engine
# checkout (for its conversion scripts) mounted.
run() {
  docker run --rm \
    -e HF_ENDPOINT -e http_proxy -e https_proxy -e no_proxy \
    -e HTTP_PROXY -e HTTPS_PROXY -e NO_PROXY -e ENGINE_WORKSPACE=/tmp \
    -v "$HF_MODEL_DIR:/hf" -v "$OV_MODEL_DIR:/ov" -v "$ENGINE_DIR:/engine:ro" \
    "$@"
}

# download REPO NAME PATTERN... -> $HF_MODEL_DIR/NAME
download() {
  local repo="$1" name="$2"
  shift 2
  log "Downloading $repo"
  run --entrypoint huggingface-cli "$IMAGE" \
    download "$repo" --include "$@" --local-dir "/hf/$name"
}

# optimum_export NAME TASK OUTPUT: $HF_MODEL_DIR/NAME -> $OV_MODEL_DIR/OUTPUT
optimum_export() {
  log "Converting $1 to OpenVINO"
  run --entrypoint optimum-cli "$IMAGE" \
    export openvino --model "/hf/$1" --task "$2" "/ov/$3"
}

# skip_if_ready NAME FILE...: true (and a message) when every FILE exists.
skip_if_ready() {
  local name="$1" file
  shift
  for file in "$@"; do
    [[ -f "$OV_MODEL_DIR/$file" ]] || return 1
  done
  log "$name is already prepared, skipping"
}

prepare_gme() {
  local out=gme-Qwen2-VL-2B-Instruct-OV
  skip_if_ready GME "$out/gme_openvino_config.json" && return
  [[ ! -e "$OV_MODEL_DIR/$out" ]] \
    || die "$OV_MODEL_DIR/$out exists but holds no gme_openvino_config.json; remove it and rerun"
  download Alibaba-NLP/gme-Qwen2-VL-2B-Instruct gme-Qwen2-VL-2B-Instruct \
    "*.json" "*.safetensors" "merges.txt"
  log "Converting GME to OpenVINO ($gme_precision)"
  run -e GME_EXPORT_PRECISION="$gme_precision" --entrypoint sh "$IMAGE" -c "
    set -e
    pip install --user -q --no-warn-script-location '$TRANSFORMERS5'
    cd /engine && PYTHONPATH=src python scripts/export_gme_ov.py \
      --checkpoint /hf/gme-Qwen2-VL-2B-Instruct --precision \"\$GME_EXPORT_PRECISION\" \
      --output-dir /ov/$out
  "
}

prepare_reranker() {
  skip_if_ready bge-reranker-large BAAI/bge-reranker-large/openvino_model.xml && return
  download BAAI/bge-reranker-large bge-reranker-large \
    "*.json" "*.safetensors" "sentencepiece.bpe.model"
  optimum_export bge-reranker-large text-classification BAAI/bge-reranker-large
}

prepare_media-reranker() {
  local name=Qwen3-VL-Reranker-2B out=Qwen3-VL-Reranker-2B-OV
  skip_if_ready "Qwen3-VL reranker" \
    "$out/reranker_text.xml" "$out/reranker_image.xml" "$out/reranker_video.xml" && return
  download Qwen/Qwen3-VL-Reranker-2B "$name" \
    "*.json" "*.safetensors" "merges.txt" "*.jinja" "scripts/*"
  log "Exporting Qwen3-VL reranker to OpenVINO (one graph per mode: text, image, video)"
  run --entrypoint sh "$IMAGE" -c "
    set -e
    # Any media file works as the trace sample: visual inputs are normalized
    # to a fixed grid and video is padded to one sequence bucket, so the
    # traced shapes do not depend on the sample's content.
    python -c '
import cv2, numpy as np
from PIL import Image
Image.new(\"RGB\", (64, 64), (120, 80, 40)).save(\"/tmp/sample.png\")
writer = cv2.VideoWriter(\"/tmp/sample.mp4\", cv2.VideoWriter_fourcc(*\"mp4v\"), 5, (64, 64))
for i in range(12):
    writer.write(np.full((64, 64, 3), i * 20, np.uint8))
writer.release()
'
    for mode in text image video; do
      sample=
      [ \"\$mode\" = image ] && sample=/tmp/sample.png
      [ \"\$mode\" = video ] && sample=/tmp/sample.mp4
      python /engine/scripts/export_qwen3_vl_reranker_ov.py \
        --source /hf/$name --output /ov/$out --mode \"\$mode\" \${sample:+--sample \"\$sample\"}
    done
  "
}

prepare_media-reranker-int8() {
  # Weight-only INT8 quantization of the FP16 package; the FP16 package is
  # built first when missing. The directory keeps the serving convention
  # (<model-id-last-component>-OV), so the engine picks it up with
  # ENGINE_MEDIA_RERANK_MODEL_ID=Qwen/Qwen3-VL-Reranker-2B-INT8.
  local fp16=Qwen3-VL-Reranker-2B-OV out=Qwen3-VL-Reranker-2B-INT8-OV
  prepare_media-reranker
  skip_if_ready "Qwen3-VL reranker INT8" \
    "$out/reranker_text.xml" "$out/reranker_image.xml" "$out/reranker_video.xml" && return
  log "Quantizing Qwen3-VL reranker to INT8 (weight-only)"
  run --entrypoint python "$IMAGE" \
    /engine/scripts/quantize_qwen3_vl_reranker_int8.py --src "/ov/$fp16" --dst "/ov/$out"
}

prepare_layout() {
  skip_if_ready PP-DocLayoutV3 PP-DocLayoutV3/pp_doclayout_v3.onnx && return
  download PaddlePaddle/PP-DocLayoutV3_safetensors PP-DocLayoutV3_safetensors \
    "*.json" "*.safetensors"
  log "Converting PP-DocLayoutV3 to ONNX"
  run --entrypoint sh "$IMAGE" -c "
    set -e
    pip install --user -q --no-warn-script-location '$TRANSFORMERS5'
    cd /engine && PYTHONPATH=src python scripts/export_pp_doclayout_v3.py \
      --model-path /hf/PP-DocLayoutV3_safetensors --output-dir /ov/PP-DocLayoutV3
  "
}

# Validate using only the container's Python standard library: no model code,
# dependency installation, compilation or inference is needed to check readiness.
validate_video_package() {
  local name="$1"
  run -i --entrypoint python "$IMAGE" - "/ov/${name}-${video_precision}" "$name" "$video_precision" <<'PY'
import json
from pathlib import Path
import sys

root = Path(sys.argv[1])
name, precision = sys.argv[2:]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate():
    metadata = json.loads((root / "video_embedding.json").read_text(encoding="utf-8"))
    require(isinstance(metadata, dict), "readiness manifest must be an object")
    model_id, dimension, context_length, preprocessing, tokenizer_type = {
        "viclip-b": ("OpenGVLab/ViCLIP-B-16-hf", 512, 32, "viclip", "clip_bpe"),
        "viclip-l": ("OpenGVLab/ViCLIP-L-14-hf", 768, 32, "viclip", "clip_bpe"),
        "cosmos-224p": ("nvidia/Cosmos-Embed1-224p", 256, 128, "cosmos", "bert"),
    }[name]
    expected = {
        "format": 1, "name": name, "model_id": model_id,
        "frames": 8, "image_size": 224, "context_length": context_length,
        "dimension": dimension, "preprocessing": preprocessing, "tokenizer_type": tokenizer_type,
    }
    for key, value in expected.items():
        require(metadata.get(key) == value, f"expected {key}={value!r}, got {metadata.get(key)!r}")
    actual_precision = metadata.get("precision")
    require(actual_precision == precision,
          f"existing precision {actual_precision!r} does not match "
          f"package {root.name!r} precision {precision!r}")
    artifacts = metadata.get("artifacts")
    require(isinstance(artifacts, dict)
            and set(artifacts) == {"video_encoder", "text_encoder", "tokenizer"},
            "manifest must declare both IR pairs and tokenizer sidecars")
    for stem in ("video_encoder", "text_encoder"):
        require(artifacts[stem] == [f"{stem}.xml", f"{stem}.bin"],
                f"expected the canonical {stem}.xml/.bin pair")
    for group, files in artifacts.items():
        require(isinstance(files, list) and files, f"empty or invalid {group} artifacts")
        for file in files:
            require(isinstance(file, str) and file not in ("", ".", "..")
                    and Path(file).name == file, f"unsafe {group} artifact: {file!r}")
            path = root / file
            require(not path.is_symlink() and path.is_file() and path.stat().st_size > 0,
                    f"missing, empty or symlinked artifact: {file}")
        require(len(files) == len(set(files)), f"duplicate {group} artifacts")
    tokenizer = set(artifacts["tokenizer"])
    required = {"tokenizer_config.json", "special_tokens_map.json"}
    required |= {"vocab.txt"} if tokenizer_type == "bert" else {"merges.txt", "vocab.json"}
    require(required <= tokenizer <= required | {"added_tokens.json"},
        f"expected standard {tokenizer_type} tokenizer sidecars")


try:
    validate()
except (OSError, ValueError, TypeError) as error:
    sys.exit(f"error: {root}: {error}; existing output left untouched")
PY
}

prepare_video() {
  local name="$1" repo exporter requirements out="$OV_MODEL_DIR/${1}-${video_precision}"
  local patterns=("*.py" "*.json" "*.safetensors" "*.gz")
  case "$name" in
    viclip-b|viclip-l)
      if [[ "$name" == viclip-b ]]; then repo=OpenGVLab/ViCLIP-B-16-hf; else repo=OpenGVLab/ViCLIP-L-14-hf; fi
      exporter=export_viclip_ov.py
      requirements=requirements-viclip-export.txt
      ;;
    cosmos-224p)
      repo=nvidia/Cosmos-Embed1-224p
      exporter=export_cosmos_ov.py
      requirements=requirements-cosmos-export.txt
      patterns=("*.py" "*.json" "*.safetensors" "*.bin" "*.txt")
      ;;
    *) die "unsupported video model '$name'" ;;
  esac
  [[ ! -L "$out" ]] || die "$out must not be a symlink; existing output left untouched"
  if [[ -e "$out" ]]; then
    [[ -d "$out" ]] || die "$out is not a directory; existing output left untouched"
    if [[ -f "$out/video_embedding.json" ]]; then
      validate_video_package "$name"
      log "$out is already prepared ($video_precision), skipping"
      return
    fi
    [[ -z "$(find "$out" -mindepth 1 -maxdepth 1 -print -quit)" ]] \
      || die "$out is nonempty but has no readiness manifest; existing output left untouched"
  fi
  download "$repo" "$name" "${patterns[@]}"
  log "WARNING: --trust-local-code executes checkpoint Python from /hf/$name; use only reviewed, trusted model source"
  log "Converting $name to OpenVINO ($video_precision) at $out"
  run -e VIDEO_MODEL_NAME="$name" -e VIDEO_EXPORT_PRECISION="$video_precision" \
    -e VIDEO_EXPORT_SCRIPT="$exporter" -e VIDEO_EXPORT_REQUIREMENTS="$requirements" \
    --entrypoint sh "$IMAGE" -c '
    set -e
    pip install --user -q --no-warn-script-location -r "/engine/scripts/$VIDEO_EXPORT_REQUIREMENTS"
    set --
    case "$VIDEO_MODEL_NAME" in viclip-b|viclip-l) set -- --model "$VIDEO_MODEL_NAME" ;; esac
    python "/engine/scripts/$VIDEO_EXPORT_SCRIPT" "$@" \
      --checkpoint "/hf/$VIDEO_MODEL_NAME" --output-dir "/ov/${VIDEO_MODEL_NAME}-${VIDEO_EXPORT_PRECISION}" \
      --precision "$VIDEO_EXPORT_PRECISION" --trust-local-code
  '
  validate_video_package "$name"
}

prepare_whisper() {
  skip_if_ready Whisper whisper-small/openvino_encoder_model.xml whisper-small/openvino_decoder_model.xml && return
  download openai/whisper-small whisper-small "*.json" "*.safetensors" "merges.txt"
  optimum_export whisper-small automatic-speech-recognition-with-past whisper-small
}

prepare_bge() {
  skip_if_ready bge-small-en-v1.5 bge-small-en-v1.5/openvino_model.xml && return
  download BAAI/bge-small-en-v1.5 bge-small-en-v1.5 "*.json" "*.safetensors" "vocab.txt"
  optimum_export bge-small-en-v1.5 feature-extraction bge-small-en-v1.5
}

for model in "${models[@]}"; do
  [[ " ${ALL_MODELS[*]} " == *" $model "* ]] || die "unknown model '$model' (one of: ${ALL_MODELS[*]})"
done
command -v docker >/dev/null 2>&1 || die "docker is required"
docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || die "image $IMAGE not found; build it first with: quickstart.sh --build"

# The containers write as UID 1000, the engine container's user.
mkdir -p "$HF_MODEL_DIR" "$OV_MODEL_DIR"
for dir in "$HF_MODEL_DIR" "$OV_MODEL_DIR"; do
  if [[ "$(stat -c %u "$dir")" != 1000 && "$(id -u)" != 1000 ]]; then
    log "Giving $dir to UID 1000 (sudo)"
    sudo chown 1000:1000 "$dir"
  fi
done

for model in "${models[@]}"; do
  case "$model" in
    viclip-b|viclip-l|cosmos-224p) prepare_video "$model" ;;
    *) "prepare_$model" ;;
  esac
done

log "Done. Models are in $OV_MODEL_DIR; $HF_MODEL_DIR can be deleted to free disk space."
