# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Export a trusted local Cosmos-Embed1-224p checkpoint to an OpenVINO package.

--checkpoint must be a complete local directory, never a Hub ID. Review its
Python before opting in with --trust-local-code: offline loading is not a
sandbox for checkpoint code. No checkpoint files are changed or downloaded.

Both towers are evaluated/traced in FP32 on CPU. --precision fp16 (default)
compresses floating weights when saving; fp32 leaves them uncompressed. No
OpenVINO compilation, dummy inference or reference inference is performed.
The format-1 video_embedding.json readiness marker is published atomically and
exclusively LAST, after both IRs and the standard slow BERT tokenizer exist.

Default output: <model-root>/cosmos-224p-<precision>. The model root follows
engine configuration: nonempty ENGINE_MODEL_ROOT_PATH, otherwise
ENGINE_WORKSPACE/models (ENGINE_WORKSPACE defaults to engine/workspace relative
to this script). No engine modules, Torch, Transformers or OpenVINO are imported
for --help. Export dependencies belong in a separate throwaway environment.

Output must be new or empty. Failed exports may leave partial files without a
readiness marker; no overwrite, resume or automatic cleanup is attempted. Do
not target the same output concurrently. Manifest publication needs filesystem
hard-link support. The constructor-local Q-Former config bridge is for
single-threaded loading only; it never patches Transformers globally.

Video preprocessing stays outside the graph: sample eight frames, RGB,
official processor-style antialiased bilinear square resize, then /255.
Preserve the processor's tensor/uint8 resize ordering for exact pixel parity.
Supply [0,1] pixels, without external ImageNet normalization: Cosmos normalizes
internally. Tokenize with right padding/truncation to 128 tokens; pass only
int64 input_ids and attention_mask. Outputs are already projected and L2-normalized.
"""

from __future__ import annotations

import argparse
import gc
import importlib
import json
import logging
import os
from pathlib import Path
import tempfile


LOGGER = logging.getLogger("export_cosmos_ov")
MODEL_NAME = "cosmos-224p"
MODEL_ID = "nvidia/Cosmos-Embed1-224p"
MANIFEST = "video_embedding.json"
FRAMES = 8
IMAGE_SIZE = 224
CONTEXT_LENGTH = 128
DIMENSION = 256
SUPPORTED_PRECISIONS = ("fp16", "fp32")


def _default_output_dir(precision: str) -> Path:
    """Mirror config.MODEL_DIR without importing config's runtime mkdir effects."""
    workspace = os.getenv(
        "ENGINE_WORKSPACE", str(Path(__file__).resolve().parents[1] / "workspace")
    )
    model_root = os.getenv("ENGINE_MODEL_ROOT_PATH") or os.path.join(workspace, "models")
    return Path(model_root) / f"{MODEL_NAME}-{precision}"


def _checkpoint_artifacts(source: Path) -> list[str]:
    """Check local architecture, code and complete weights before executing Python."""
    config = json.loads((source / "config.json").read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("Checkpoint config.json must contain an object")
    actual = (config.get("model_type"), config.get("resolution"),
              config.get("num_video_frames"), config.get("max_txt_len"),
              config.get("embed_dim"))
    if actual != ("cosmos-embed1", IMAGE_SIZE, FRAMES, CONTEXT_LENGTH, DIMENSION):
        raise ValueError(f"Expected the local Cosmos-Embed1-224p architecture, got {actual}")
    expected = {
        "AutoConfig": "configuration_embed1.CosmosEmbed1Config",
        "AutoModel": "modeling_embed1.CosmosEmbed1",
        "AutoProcessor": "preprocessing_embed1.CosmosEmbed1Processor",
    }
    auto_map = config.get("auto_map")
    if not isinstance(auto_map, dict) or any(auto_map.get(k) != v for k, v in expected.items()):
        raise ValueError("Expected checkpoint-local Cosmos classes, not external auto_map references")
    required = {
        "config.json", "configuration_embed1.py", "modeling_embed1.py",
        "modeling_outputs.py", "modeling_qformer.py", "modeling_utils.py",
        "modeling_vit.py", "preprocessing_embed1.py", "processor_config.json",
        "tokenizer_config.json", "vocab.txt", "special_tokens_map.json",
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
                or any(not isinstance(key, str) or not key for key in weight_map)
                or any(not isinstance(shard, str) or not shard
                       or Path(shard).name != shard or shard in (".", "..")
                       or "\\" in shard for shard in weight_map.values())):
            raise ValueError(f"Expected checkpoint-local weight shards in {name}")
        weights.update(weight_map.values())
    if not weights:
        raise FileNotFoundError("Expected local model.safetensors or pytorch_model.bin (or shards)")
    missing = sorted(name for name in required | weights if not (source / name).is_file())
    if missing:
        raise FileNotFoundError(f"Incomplete local checkpoint: {', '.join(missing)}")
    empty = sorted(name for name in required | weights if (source / name).stat().st_size == 0)
    if empty:
        raise ValueError(f"Empty local checkpoint artifacts: {', '.join(empty)}")
    return sorted(required | weights)


def _empty_output(path: Path, source: Path, precision: str) -> Path:
    if path.is_symlink():
        raise ValueError("--output-dir must not be a symlink")
    out = path.resolve()
    if out == source or out in source.parents or source in out.parents:
        raise ValueError("--output-dir must not overlap the checkpoint directory")
    suffix = out.name.rsplit("-", 1)[-1]
    if suffix in SUPPORTED_PRECISIONS and suffix != precision:
        raise ValueError("Output directory precision must match --precision")
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


def _save_runtime_tokenizer(tokenizer, out: Path) -> list[str]:
    """Save/reload ordinary slow BERT files without checkpoint Python sidecars."""
    from transformers import AutoTokenizer, BertTokenizer

    if type(tokenizer) is not BertTokenizer:
        raise ValueError("Expected a standard slow BertTokenizer")
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
        "vocab.txt", "tokenizer_config.json", "special_tokens_map.json", "added_tokens.json",
    }
    required = {"vocab.txt", "tokenizer_config.json", "special_tokens_map.json"}
    if (not required.issubset(files) or set(files) - allowed
            or any((out / name).is_symlink() or not (out / name).is_file()
                   or (out / name).stat().st_size == 0 for name in files)):
        raise ValueError(f"Unexpected or incomplete tokenizer sidecars: {files}")
    reloaded = AutoTokenizer.from_pretrained(
        str(out), local_files_only=True, use_fast=False, trust_remote_code=False
    )
    if (type(reloaded) is not type(tokenizer)
            or reloaded.get_vocab() != tokenizer.get_vocab()
            or reloaded.special_tokens_map != tokenizer.special_tokens_map
            or reloaded.all_special_ids != tokenizer.all_special_ids
            or reloaded.model_max_length != CONTEXT_LENGTH
            or reloaded.pad_token_id != 0
            or reloaded.bos_token_id != tokenizer.bos_token_id
            or reloaded.eos_token_id != tokenizer.eos_token_id
            or reloaded.padding_side != "right" or reloaded.truncation_side != "right"
            or reloaded.do_basic_tokenize != tokenizer.do_basic_tokenize):
        raise ValueError("Standalone slow-tokenizer round trip changed its Cosmos contract")
    if tokenizer.do_basic_tokenize:
        for attribute in ("do_lower_case", "never_split", "tokenize_chinese_chars", "strip_accents"):
            if (getattr(reloaded.basic_tokenizer, attribute)
                    != getattr(tokenizer.basic_tokenizer, attribute)):
                raise ValueError(f"Standalone BERT tokenizer changed {attribute}")
    if (reloaded.bos_token != "[DEC]" or reloaded.bos_token_id != 30522
            or reloaded.cls_token_id != 101 or reloaded.sep_token_id != 102):
        raise ValueError("Cosmos requires the original [DEC], CLS and SEP token IDs")
    return files


def _load_model(source: Path):
    import torch
    from transformers import AutoConfig, AutoProcessor, BertTokenizer
    from transformers.dynamic_module_utils import get_class_from_dynamic_module

    config = AutoConfig.from_pretrained(
        str(source), trust_remote_code=True, local_files_only=True
    )
    # Change only this in-memory config, never checkpoint files or globals.
    config.transformer_engine = False
    config.use_fp8 = False
    processor = AutoProcessor.from_pretrained(
        str(source), trust_remote_code=True, local_files_only=True,
        use_fast=False, resolution=IMAGE_SIZE, num_video_frames=FRAMES,
        max_txt_len=CONTEXT_LENGTH,
    )
    tokenizer = processor.tokenizer
    if (type(tokenizer) is not BertTokenizer or len(tokenizer) != config.vocab_size
            or tokenizer.pad_token_id != 0
            or tokenizer.bos_token != "[DEC]" or tokenizer.bos_token_id != 30522
            or tokenizer.cls_token_id != 101 or tokenizer.sep_token_id != 102):
        raise ValueError("Cosmos requires its complete local slow BERT tokenizer, including [DEC] and pad 0")
    model_class = get_class_from_dynamic_module(
        "modeling_embed1.CosmosEmbed1", str(source), local_files_only=True
    )
    # The complete Q-Former weights are local, but its constructor asks for
    # BertConfig.from_pretrained('bert-base-uncased'). The default config is
    # equivalent; Cosmos supplies the remaining fields. Patch only this loaded
    # checkpoint module's binding for construction, never Transformers itself.
    package = model_class.__module__.rpartition(".")[0]
    qformer_module = importlib.import_module(f"{package}.modeling_qformer")
    original = qformer_module.BertConfig

    class LocalBertConfig(original):
        @classmethod
        def from_pretrained(cls, name, *args, **kwargs):
            if name != "bert-base-uncased" or args or kwargs:
                raise ValueError(f"Unsupported offline Cosmos Q-Former config request: {name!r}")
            return original()

    qformer_module.BertConfig = LocalBertConfig
    try:
        model = _strict_model(model_class.from_pretrained(
            str(source), config=config, local_files_only=True, torch_dtype=torch.float32,
            output_loading_info=True, ignore_mismatched_sizes=False,
        ), MODEL_ID)
    finally:
        qformer_module.BertConfig = original
    if model.transformer_engine or model.use_fp8:
        raise ValueError("Cosmos export requires the standard PyTorch path, without TE/FP8")
    actual = (model.config.model_type, model.config.resolution,
              model.config.num_video_frames, model.config.max_txt_len, model.config.embed_dim)
    if actual != ("cosmos-embed1", IMAGE_SIZE, FRAMES, CONTEXT_LENGTH, DIMENSION):
        raise ValueError(f"Unexpected Cosmos encoder dimensions: {actual}")
    model.to(device="cpu", dtype=torch.float32).eval().requires_grad_(False)
    for module in model.modules():
        if hasattr(module, "checkpoint_num"):
            module.checkpoint_num = 0
        for flag in ("gradient_checkpointing", "checkpoint_activations", "checkpoint_attention"):
            if hasattr(module, flag):
                setattr(module, flag, False)
    return model, tokenizer


def _export_towers(model, tokenizer, out: Path, precision: str) -> None:
    import openvino as ov
    import torch

    # Keep Module subclasses local so importing this script never imports Torch.
    class CosmosVideoTower(torch.nn.Module):
        def __init__(self, base):
            super().__init__()
            self.model = base

        def forward(self, pixel_values):
            # Resized RGB / 255, NOT ImageNet-normalized: Cosmos does that internally.
            return self.model.get_video_embeddings(pixel_values).visual_proj

    class CosmosTextTower(torch.nn.Module):
        def __init__(self, base):
            super().__init__()
            self.model = base

        def forward(self, input_ids, attention_mask):
            # token_type_ids is not consumed and must not enter the graph.
            return self.model.get_text_embeddings(input_ids, attention_mask).text_proj

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

    video_tower = CosmosVideoTower(model)
    export(
        video_tower,
        torch.zeros(1, FRAMES, 3, IMAGE_SIZE, IMAGE_SIZE, dtype=torch.float32, device="cpu"),
        [("pixel_values", ov.PartialShape([1, FRAMES, 3, IMAGE_SIZE, IMAGE_SIZE]), ov.Type.f32)],
        "video_encoder", ov.PartialShape([1, DIMENSION]),
    )
    del video_tower
    ids = torch.full((2, CONTEXT_LENGTH), tokenizer.pad_token_id, dtype=torch.int64, device="cpu")
    ids[:, 0] = tokenizer.cls_token_id
    ids[:, 1] = tokenizer.sep_token_id
    inputs = [
        ("input_ids", ov.PartialShape([-1, CONTEXT_LENGTH]), ov.Type.i64),
        ("attention_mask", ov.PartialShape([-1, CONTEXT_LENGTH]), ov.Type.i64),
    ]
    example = (ids, (ids != tokenizer.pad_token_id).to(dtype=torch.int64))
    export(
        CosmosTextTower(model), example, inputs,
        "text_encoder", ov.PartialShape([-1, DIMENSION]),
    )


def export_package(
    checkpoint: str | Path,
    output_dir: str | Path,
    precision: str = "fp16",
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
    if precision not in SUPPORTED_PRECISIONS:
        raise ValueError(f"Cosmos precision must be one of {SUPPORTED_PRECISIONS}, got {precision!r}")
    source = Path(checkpoint).expanduser().resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"--checkpoint must be an existing complete local directory: {source}")
    output_path = Path(output_dir).expanduser()
    out = _empty_output(output_path, source, precision)
    source_artifacts = _checkpoint_artifacts(source)
    # Set BEFORE importing Transformers/Hub, including via checkpoint Python.
    # Trusted local code can still do arbitrary things; this is not a sandbox.
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    LOGGER.info("Loading %s from %s for FP32 CPU tracing", MODEL_NAME, source)
    model, tokenizer = _load_model(source)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    if parameter_count <= 0:
        raise ValueError("Expected a positive full-model parameter count")
    # Loading may be long: recheck the original path, including its symlink status.
    if _empty_output(output_path, source, precision) != out:
        raise ValueError("--output-dir changed while loading the checkpoint")
    out.mkdir(parents=True, exist_ok=True)
    _export_towers(model, tokenizer, out, precision)
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
        "name": MODEL_NAME,
        "model_id": MODEL_ID,
        "frames": FRAMES,
        "image_size": IMAGE_SIZE,
        "context_length": CONTEXT_LENGTH,
        "dimension": DIMENSION,
        "precision": precision,
        "preprocessing": "cosmos",
        "tokenizer_type": "bert",
        "parameter_count": parameter_count,
        "source_artifacts": source_artifacts,
        "artifacts": {"video_encoder": ir_files[:2], "text_encoder": ir_files[2:],
                      "tokenizer": tokenizer_files},
    }
    # Same-filesystem exclusive hard link: never overwrite readiness and never
    # expose truncated JSON if serialization or a write fails. Publish LAST.
    with tempfile.TemporaryDirectory(prefix=f".{MODEL_NAME}-manifest-", dir=out.parent) as temporary:
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
    parser.add_argument("--checkpoint", type=Path, required=True,
                        help="Complete local checkpoint directory; never downloaded or modified")
    parser.add_argument("--output-dir", type=Path,
                        help="New/empty package directory (default: <model-root>/cosmos-224p-<precision>)")
    parser.add_argument("--precision", choices=SUPPORTED_PRECISIONS, default="fp16",
                        help="Stored floating-weight precision (default: %(default)s)")
    parser.add_argument("--trust-local-code", action="store_true", required=True,
                        help="Allow reviewed checkpoint Python to execute; not sandboxed")
    args = parser.parse_args()
    output = args.output_dir if args.output_dir is not None else _default_output_dir(args.precision)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    export_package(args.checkpoint, output, args.precision,
                   trust_local_code=args.trust_local_code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())