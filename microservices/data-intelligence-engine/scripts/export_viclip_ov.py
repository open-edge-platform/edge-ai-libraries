# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Export a trusted local ViCLIP-B/L checkpoint to a standalone OpenVINO package.

--checkpoint must be a complete local directory, never a Hub ID. Review its
Python before opting in with --trust-local-code: offline loading is not a
sandbox for checkpoint code. No checkpoint files are changed or downloaded.

Both towers are evaluated/traced in FP32 on CPU. --precision fp16 (default)
compresses floating weights when saving; fp32 leaves them uncompressed. No
OpenVINO compilation, dummy inference or reference inference is performed.
The format-1 video_embedding.json readiness marker is published atomically and
exclusively LAST, after both IRs and the standard slow CLIP tokenizer exist.

Default output: <model-root>/<model>-<precision>. The model root follows engine
configuration: nonempty ENGINE_MODEL_ROOT_PATH, otherwise ENGINE_WORKSPACE/models
(ENGINE_WORKSPACE defaults to engine/workspace relative to this script).
No engine modules, Torch, Transformers or OpenVINO are imported for --help.

Output must be new or empty. Failed exports may leave partial files without a
readiness marker; no overwrite, resume or automatic cleanup is attempted. Do
not target the same output concurrently. Manifest publication needs filesystem
hard-link support. Runtime preprocessing and L2 normalization stay outside the
graphs: square-resized RGB, eight 224px frames, ImageNet mean/std; text callers
must apply ftfy.fix_text followed by double HTML unescaping, as upstream does.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import gc
import gzip
import json
import logging
import os
from pathlib import Path
import tempfile


LOGGER = logging.getLogger("export_viclip_ov")
MANIFEST = "video_embedding.json"
FRAMES = 8
IMAGE_SIZE = 224
CONTEXT_LENGTH = 32
SUPPORTED_PRECISIONS = ("fp16", "fp32")


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    size: str
    dimension: int


MODELS = {
    "viclip-b": ModelSpec("OpenGVLab/ViCLIP-B-16-hf", "b", 512),
    "viclip-l": ModelSpec("OpenGVLab/ViCLIP-L-14-hf", "l", 768),
}


def _default_output_dir(model_name: str, precision: str) -> Path:
    """Mirror config.MODEL_DIR without importing config's runtime mkdir effects."""
    workspace = os.getenv(
        "ENGINE_WORKSPACE", str(Path(__file__).resolve().parents[1] / "workspace")
    )
    model_root = os.getenv("ENGINE_MODEL_ROOT_PATH") or os.path.join(workspace, "models")
    return Path(model_root) / f"{model_name}-{precision}"


def _checkpoint_artifacts(source: Path, spec: ModelSpec) -> list[str]:
    """Check local architecture, code and complete weights before executing Python."""
    config = json.loads((source / "config.json").read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Checkpoint config.json must contain an object")
    if str(config.get("size", "")).lower() != spec.size:
        raise ValueError(f"Expected ViCLIP size={spec.size!r} for {spec.model_id}")
    expected = {"AutoConfig": "configuration_viclip.Config", "AutoModel": "viclip.ViCLIP"}
    auto_map = config.get("auto_map")
    if not isinstance(auto_map, dict) or any(auto_map.get(k) != v for k, v in expected.items()):
        raise ValueError("Expected checkpoint-local ViCLIP classes, not external auto_map references")
    required = {
        "config.json", "configuration_viclip.py", "viclip.py", "viclip_vision.py",
        "viclip_text.py", "simple_tokenizer.py", "bpe_simple_vocab_16e6.txt.gz",
    }
    weights = set()
    for name in ("model.safetensors", "pytorch_model.bin"):
        if (source / name).is_file():
            weights.add(name)
    for name in ("model.safetensors.index.json", "pytorch_model.bin.index.json"):
        index_path = source / name
        if not index_path.is_file():
            continue
        weights.add(name)
        index = json.loads(index_path.read_text(encoding="utf-8"))
        weight_map = index.get("weight_map") if isinstance(index, dict) else None
        if (not isinstance(weight_map, dict) or not weight_map
                or any(not isinstance(shard, str) or Path(shard).name != shard
                       or shard in (".", "..") for shard in weight_map.values())):
            raise ValueError(f"Expected checkpoint-local weight shards in {name}")
        weights.update(weight_map.values())
    if not weights:
        raise FileNotFoundError("Expected local model.safetensors or pytorch_model.bin (or shards)")
    missing = sorted(name for name in required | weights if not (source / name).is_file())
    if missing:
        raise FileNotFoundError(f"Incomplete local checkpoint: {', '.join(missing)}")
    return sorted(required | weights)


def _empty_output(path: Path, source: Path, model_name: str, precision: str) -> Path:
    if path.is_symlink():
        raise ValueError("--output-dir must not be a symlink")
    out = path.resolve()
    if out == source or out in source.parents or source in out.parents:
        raise ValueError("--output-dir must not overlap the checkpoint directory")
    suffix = out.name.rsplit("-", 1)[-1]
    if suffix in SUPPORTED_PRECISIONS and suffix != precision:
        raise ValueError("Output directory precision must match --precision")
    canonical_packages = {f"{name}-{dtype}" for name in MODELS for dtype in SUPPORTED_PRECISIONS}
    if ((out.name in canonical_packages and out.name != f"{model_name}-{precision}")
            or (out.name in MODELS and out.name != model_name)):
        raise ValueError("Output directory model identity must match --model")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise ValueError("--output-dir requires a new or empty directory; packages are never overwritten")
    return out


def _strict_model(result, model_id: str):
    if not isinstance(result, tuple) or len(result) != 2:
        raise ValueError(f"{model_id} did not return output_loading_info=True results")
    model, info = result
    if not isinstance(info, dict):
        raise ValueError(f"{model_id} did not provide checkpoint loading diagnostics")
    problems = {key: value for key, value in info.items() if value}
    if problems:
        raise ValueError(f"{model_id} checkpoint did not load exactly: {problems}")
    return model


def _build_viclip_tokenizer(bpe_path: Path, reference):
    """Preserve SimpleTokenizer's byte vocabulary and exact merge-rank order."""
    import ftfy  # CLIPTokenizer's BasicTokenizer fallback is not equivalent.
    from transformers import CLIPTokenizer
    from transformers.models.clip.tokenization_clip import bytes_to_unicode

    del ftfy
    with gzip.open(bpe_path, "rt", encoding="utf-8") as source:
        # Upstream's exact slice: 48,894 merges, NOT the entire gzip vocabulary.
        lines = source.read().split("\n")[1 : 49152 - 256 - 2 + 1]
    merges = [tuple(line.split()) for line in lines]
    if len(merges) != 48894 or any(len(pair) != 2 for pair in merges):
        raise ValueError("ViCLIP requires the original 48,894 CLIP BPE merges")
    byte_encoder = bytes_to_unicode()
    vocabulary = list(byte_encoder.values())
    vocabulary += [token + "</w>" for token in vocabulary]
    vocabulary += ["".join(pair) for pair in merges]
    vocabulary += ["<|startoftext|>", "<|endoftext|>"]
    vocab = dict(zip(vocabulary, range(len(vocabulary))))
    ranks = dict(zip(merges, range(len(merges))))
    if (len(vocab) != 49408 or vocab["!"] != 0
            or vocab != reference.encoder or ranks != reference.bpe_ranks
            or byte_encoder != reference.byte_encoder):
        raise ValueError("Checkpoint SimpleTokenizer vocabulary/merges are not standard CLIP")

    with tempfile.TemporaryDirectory(prefix="viclip-tokenizer-") as temporary:
        root = Path(temporary)
        (root / "vocab.json").write_text(
            json.dumps(vocab, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        (root / "merges.txt").write_text(
            "#version: 0.2\n" + "\n".join(" ".join(pair) for pair in merges) + "\n",
            encoding="utf-8",
        )
        tokenizer = CLIPTokenizer(
            vocab_file=str(root / "vocab.json"),
            merges_file=str(root / "merges.txt"),
            pad_token="!",  # Upstream pads with zero, never EOS (49407).
            model_max_length=CONTEXT_LENGTH,
            padding_side="right",
            truncation_side="right",  # Reserves the final token for EOS.
            # Literal exclamation marks must still go through BPE, not padding.
            split_special_tokens=True,
            clean_up_tokenization_spaces=False,
        )
    # Both pinned regexes split SINGLE digits. Do not silently accept a variant.
    if (tokenizer.pat.pattern != reference.pat.pattern
            or tokenizer.pat.flags != reference.pat.flags
            or tokenizer.encoder != vocab or tokenizer.bpe_ranks != ranks
            or tokenizer.byte_encoder != byte_encoder or tokenizer.fix_text is None
            or (tokenizer.pad_token_id, tokenizer.bos_token_id, tokenizer.eos_token_id)
            != (0, 49406, 49407) or not tokenizer.split_special_tokens):
        raise ValueError("Installed CLIPTokenizer is incompatible with local SimpleTokenizer")
    return tokenizer


def _save_runtime_tokenizer(tokenizer, out: Path) -> list[str]:
    """Save/reload ordinary slow CLIP files without checkpoint Python sidecars."""
    from transformers import AutoTokenizer, CLIPTokenizer

    if not isinstance(tokenizer, CLIPTokenizer):
        raise ValueError("Expected a standard slow CLIPTokenizer")
    tokenizer.model_max_length = CONTEXT_LENGTH
    tokenizer.padding_side = "right"
    tokenizer.truncation_side = "right"
    tokenizer._auto_class = None
    tokenizer._auto_map = None
    tokenizer._processor_class = None
    for key in ("auto_map", "processor_class", "tokenizer_file", "name_or_path"):
        tokenizer.init_kwargs.pop(key, None)
    before = {path.name for path in out.iterdir()}
    tokenizer.save_pretrained(str(out))
    files = sorted({path.name for path in out.iterdir()} - before)
    allowed = {
        "vocab.json", "merges.txt", "tokenizer_config.json",
        "special_tokens_map.json", "added_tokens.json",
    }
    required = {"vocab.json", "merges.txt", "tokenizer_config.json", "special_tokens_map.json"}
    if not required.issubset(files) or set(files) - allowed:
        raise ValueError(f"Unexpected or incomplete tokenizer sidecars: {files}")
    reloaded = AutoTokenizer.from_pretrained(
        str(out), local_files_only=True, use_fast=False, trust_remote_code=False
    )
    if (type(reloaded) is not type(tokenizer)
            or reloaded.get_vocab() != tokenizer.get_vocab()
            or reloaded.model_max_length != CONTEXT_LENGTH
            or reloaded.pad_token_id != 0
            or reloaded.bos_token_id != 49406 or reloaded.eos_token_id != 49407
            or reloaded.padding_side != "right" or reloaded.truncation_side != "right"
            or not reloaded.split_special_tokens
            or reloaded.encoder != tokenizer.encoder
            or reloaded.bpe_ranks != tokenizer.bpe_ranks
            or reloaded.byte_encoder != tokenizer.byte_encoder
            or reloaded.pat.pattern != tokenizer.pat.pattern
            or reloaded.pat.flags != tokenizer.pat.flags or reloaded.fix_text is None):
        raise ValueError("Standalone slow-tokenizer round trip changed its ViCLIP contract")
    return files


def _load_model(source: Path, spec: ModelSpec):
    import torch
    from transformers import AutoConfig, AutoModel

    config = AutoConfig.from_pretrained(
        str(source), trust_remote_code=True, local_files_only=True
    )
    # Both source SimpleTokenizers must use the checkpoint-local gzip, not CWD.
    config.tokenizer_path = str(source / "bpe_simple_vocab_16e6.txt.gz")
    model = _strict_model(AutoModel.from_pretrained(
        str(source), config=config, trust_remote_code=True, local_files_only=True,
        torch_dtype=torch.float32, output_loading_info=True, ignore_mismatched_sizes=False,
    ), spec.model_id)
    actual = (model.video_input_num_frames, model.inputs_image_res,
              model.max_txt_l, model.vision_encoder.output_dim,
              model.text_encoder.text_projection.shape[-1])
    if actual != (FRAMES, IMAGE_SIZE, CONTEXT_LENGTH, spec.dimension, spec.dimension):
        raise ValueError(f"Unexpected ViCLIP encoder dimensions: {actual}")
    reference = model.text_encoder._tokenizer
    if (model.tokenizer.encoder != reference.encoder
            or model.tokenizer.bpe_ranks != reference.bpe_ranks
            or model.tokenizer.byte_encoder != reference.byte_encoder
            or model.tokenizer.pat.pattern != reference.pat.pattern
            or model.tokenizer.pat.flags != reference.pat.flags):
        raise ValueError("ViCLIP's two source tokenizers disagree")
    tokenizer = _build_viclip_tokenizer(Path(config.tokenizer_path), reference)
    model.to(device="cpu", dtype=torch.float32).eval().requires_grad_(False)
    for module in model.modules():
        for count in ("checkpoint_num", "vision_encoder_checkpoint_num"):
            if hasattr(module, count):
                setattr(module, count, 0)
        for flag in ("gradient_checkpointing", "checkpoint_activations", "checkpoint_attention"):
            if hasattr(module, flag):
                setattr(module, flag, False)
    return model, tokenizer


def _export_towers(model, tokenizer, spec: ModelSpec, out: Path, precision: str) -> None:
    import openvino as ov
    import torch

    # Keep Module subclasses local so importing this script never imports Torch.
    class ViCLIPVideoTower(torch.nn.Module):
        def __init__(self, base):
            super().__init__()
            self.model = base

        def forward(self, pixel_values):
            # Already square-resized and ImageNet-normalized by the caller.
            return self.model.encode_vision(pixel_values, test=True)

    class ViCLIPTextTower(torch.nn.Module):
        def __init__(self, base):
            super().__init__()
            self.text_encoder = base.text_encoder

        def forward(self, input_ids):
            return self.text_encoder(input_ids)

    def export(tower, example, inputs, stem, output_shape):
        with torch.no_grad():
            ir = ov.convert_model(tower.eval(), example_input=example, input=inputs)
        if len(ir.inputs) != len(inputs) or len(ir.outputs) != 1:
            raise ValueError(f"{stem} must expose only its declared inputs and one tensor output")
        for port, (name, shape, dtype) in zip(ir.inputs, inputs):
            if port.get_partial_shape() != shape or port.get_element_type() != dtype:
                raise ValueError(f"{stem}: unexpected shape/type for {name}")
            port.get_tensor().set_names({name})
        output = ir.output(0)
        if (output.get_partial_shape() != output_shape
                or output.get_element_type() != ov.Type.f32):
            raise ValueError(
                f"{stem}: expected FP32 {output_shape} embeddings, got "
                f"{output.get_element_type()} {output.get_partial_shape()}"
            )
        output.get_tensor().set_names({"embeddings"})
        ov.save_model(ir, out / f"{stem}.xml", compress_to_fp16=precision == "fp16")
        del ir
        gc.collect()
        LOGGER.info("Exported %s to %s", stem, out / f"{stem}.xml")

    video_tower = ViCLIPVideoTower(model)
    export(
        video_tower,
        torch.zeros(1, FRAMES, 3, IMAGE_SIZE, IMAGE_SIZE, dtype=torch.float32, device="cpu"),
        [("pixel_values", ov.PartialShape([1, FRAMES, 3, IMAGE_SIZE, IMAGE_SIZE]), ov.Type.f32)],
        "video_encoder", ov.PartialShape([1, spec.dimension]),
    )
    del video_tower
    ids = torch.full((2, CONTEXT_LENGTH), tokenizer.pad_token_id, dtype=torch.int64, device="cpu")
    ids[:, 0] = tokenizer.bos_token_id
    ids[:, 1] = tokenizer.eos_token_id
    export(
        ViCLIPTextTower(model), (ids,),
        [("input_ids", ov.PartialShape([-1, CONTEXT_LENGTH]), ov.Type.i64)],
        "text_encoder", ov.PartialShape([-1, spec.dimension]),
    )


def export_package(
    checkpoint: str | Path,
    output_dir: str | Path,
    precision: str = "fp16",
    model_name: str = "viclip-b",
    *,
    trust_local_code: bool = False,
) -> Path:
    """Export a complete local checkpoint and return the absolute package path.

    Trust and all file-only preflight checks precede heavy imports. The package
    contains only IR weights and standard tokenizer files; source_artifacts in
    the manifest is provenance, not a list of files to copy. Failures never
    publish readiness or clean up/overwrite an existing package.
    """
    if not trust_local_code:
        raise ValueError("Explicit --trust-local-code is required after reviewing checkpoint Python")
    if model_name not in MODELS:
        raise ValueError(f"ViCLIP model_name must be one of {tuple(MODELS)}, got {model_name!r}")
    if precision not in SUPPORTED_PRECISIONS:
        raise ValueError(f"ViCLIP precision must be one of {SUPPORTED_PRECISIONS}, got {precision!r}")
    source = Path(checkpoint).expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"--checkpoint must be an existing complete local directory: {source}")
    output_path = Path(output_dir).expanduser()
    out = _empty_output(output_path, source, model_name, precision)
    spec = MODELS[model_name]
    source_artifacts = _checkpoint_artifacts(source, spec)
    # Set BEFORE importing Transformers/Hub, including via checkpoint Python.
    # Trusted local code can still do arbitrary things; this is not a sandbox.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    LOGGER.info("Loading %s from %s for FP32 CPU tracing", model_name, source)
    model, tokenizer = _load_model(source, spec)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count <= 0:
        raise ValueError("Expected a positive full-model parameter count")
    # Loading may be long: recheck the original path, including its symlink status.
    if _empty_output(output_path, source, model_name, precision) != out:
        raise ValueError("--output-dir changed while loading the checkpoint")
    out.mkdir(parents=True, exist_ok=True)
    _export_towers(model, tokenizer, spec, out, precision)
    tokenizer_files = _save_runtime_tokenizer(tokenizer, out)
    ir_files = [f"{stem}.{suffix}" for stem in ("video_encoder", "text_encoder")
                for suffix in ("xml", "bin")]
    expected_files = set(ir_files + tokenizer_files)
    if ({path.name for path in out.iterdir()} != expected_files
            or any((out / name).is_symlink() or not (out / name).is_file()
                   or (out / name).stat().st_size == 0 for name in expected_files)):
        raise ValueError("Incomplete package or unexpected artifacts; readiness manifest not written")
    manifest = {
        "format": 1,
        "name": model_name,
        "model_id": spec.model_id,
        "frames": FRAMES,
        "image_size": IMAGE_SIZE,
        "context_length": CONTEXT_LENGTH,
        "dimension": spec.dimension,
        "precision": precision,
        "preprocessing": "viclip",
        "tokenizer_type": "clip_bpe",
        "parameter_count": parameter_count,
        "source_artifacts": source_artifacts,
        "artifacts": {"video_encoder": ir_files[:2], "text_encoder": ir_files[2:],
                      "tokenizer": tokenizer_files},
    }
    # Same-filesystem exclusive hard link: never overwrite readiness and never
    # expose truncated JSON if serialization or a write fails. Publish LAST.
    with tempfile.TemporaryDirectory(prefix=f".{model_name}-manifest-", dir=out.parent) as temporary:
        ready = Path(temporary) / MANIFEST
        with ready.open("x", encoding="utf-8") as target:
            target.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
            target.flush()
            os.fsync(target.fileno())
        os.link(ready, out / MANIFEST)
    LOGGER.info("Ready: %s (%s full-model parameters; %s weights)",
                out, f"{parameter_count:,}", precision)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", choices=tuple(MODELS), default="viclip-b",
                        help="Model family selector, not a checkpoint path (default: %(default)s)")
    parser.add_argument("--checkpoint", type=Path, required=True,
                        help="Complete local checkpoint directory; never downloaded or modified")
    parser.add_argument("--output-dir", type=Path,
                        help="New/empty package directory (default: <model-root>/<model>-<precision>)")
    parser.add_argument("--precision", choices=SUPPORTED_PRECISIONS, default="fp16",
                        help="Stored floating-weight precision (default: %(default)s)")
    parser.add_argument("--trust-local-code", action="store_true", required=True,
                        help="Allow reviewed checkpoint Python to execute; not sandboxed")
    args = parser.parse_args()
    output = args.output_dir if args.output_dir is not None else _default_output_dir(args.model, args.precision)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    export_package(args.checkpoint, output, args.precision, args.model,
                   trust_local_code=args.trust_local_code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())