# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Export gme-Qwen2-VL-2B-Instruct to the OpenVINO package ``gme_runtime`` loads.

GME is split into two IRs rather than converted as one graph:

* ``gme_language_<precision>.xml``: token lookup, visual-token insertion,
  decoder, last-valid-token pooling and L2 normalization.
* ``gme_visual_<precision>.xml``: the Qwen2-VL vision tower, returning the
  merged image-token embeddings the language IR consumes.

Splitting keeps the conversion-memory peak down and lets the runtime run the
visual IR once per image. Both are traced with the graph-level rewrites the
GME OpenVINO export project validated as bit-identical to the plain export
(causal SDPA for the decoder, mask-free head-first SDPA for the vision tower).
Weights are then compressed to ``weight_format`` and the result is checked
against the PyTorch model before the package is published.
"""

from __future__ import annotations

import contextlib
import gc
import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np
import openvino as ov
import torch
import torch.nn.functional as functional
from PIL import Image

from .gme_runtime import DEFAULT_INSTRUCTION, IMAGE_FACTOR, GmeOpenVINO
from ..utils import logger

SUPPORTED_WEIGHT_FORMATS = ("fp32", "int8")
MIN_IMAGE_TOKENS = 256
MAX_IMAGE_TOKENS = 1280
MAX_LENGTH = 1800
PROCESSOR_ASSETS = (
    "config.json",
    "preprocessor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "added_tokens.json",
    "chat_template.json",
    "vocab.json",
    "merges.txt",
)
# Safetensors weights plus the processor assets; the checkpoint's remote code is
# not needed, transformers loads it as a native qwen2_vl model.
CHECKPOINT_PATTERNS = ["*.json", "*.safetensors", "merges.txt"]
# Minimum cosine against PyTorch for the exported pipeline. INT8 measured >= 0.993
# on images and 0.998 on fused inputs; a broken trace lands far below either.
MIN_REFERENCE_COSINE = {"fp32": 0.9999, "int8": 0.99}


class GmeLanguageEmbed(torch.nn.Module):
    """Decoder path for text, image and fused embeddings.

    With ``causal_attention`` the explicit attention mask is dropped and SDPA is
    exported with ``causal=True``. That is an identity here: the package is
    right-padded and pooling reads the last valid token, so every padding
    position is already excluded by causality. ``position_ids`` are passed as
    ``arange(S)``, which matches what ``get_rope_index()`` derives under right
    padding. The mask input stays on the signature to select the pooled token.
    """

    def __init__(self, base: torch.nn.Module, causal_attention: bool = False) -> None:
        super().__init__()
        self.base = base
        self.image_token_id = base.config.image_token_id
        self.causal_attention = causal_attention
        self.embed_tokens = base.model.get_input_embeddings()

    def forward(self, input_ids, attention_mask, image_embeds):
        inputs_embeds = self.embed_tokens(input_ids)
        image_mask = (input_ids.reshape(-1) == self.image_token_id).unsqueeze(1)
        flat_embeds = inputs_embeds.reshape(-1, inputs_embeds.shape[-1])
        flat_embeds = flat_embeds.masked_scatter(image_mask, image_embeds.to(dtype=flat_embeds.dtype).reshape(-1))
        inputs_embeds = flat_embeds.reshape_as(inputs_embeds)
        if self.causal_attention:
            batch, seq_len = inputs_embeds.shape[0], inputs_embeds.shape[1]
            # Qwen2-VL's M-RoPE takes [3, batch, seq].
            position_ids = torch.arange(seq_len, device=inputs_embeds.device).view(1, 1, -1).expand(3, batch, -1)
            outputs = self.base.model(
                input_ids=None,
                attention_mask=None,
                position_ids=position_ids,
                inputs_embeds=inputs_embeds,
                use_cache=False,
            )
        else:
            outputs = self.base.model(
                input_ids=None,
                attention_mask=attention_mask,
                position_ids=None,
                inputs_embeds=inputs_embeds,
                use_cache=False,
            )
        sequence_lengths = attention_mask.sum(dim=1) - 1
        embedding = outputs.last_hidden_state[torch.arange(outputs.last_hidden_state.shape[0]), sequence_lengths]
        return functional.normalize(embedding, p=2, dim=1)


class GmeVisualEncoder(torch.nn.Module):
    """Vision tower returning only the merged ``[K, hidden]`` image tokens.

    transformers 5 returns ``BaseModelOutputWithPooling``; tracing it as-is would
    export the unmerged hidden state as output 0, which the runtime would then
    feed to the language IR at the wrong width.

    With ``traceable_positions`` the rotary position ids are computed here and
    passed in: transformers' own ``get_vision_position_ids`` reads the grid with
    ``tolist()``, which would bake the trace's image size into the graph.
    """

    def __init__(self, visual: torch.nn.Module, traceable_positions: bool = False) -> None:
        super().__init__()
        self.visual = visual
        self.traceable_positions = traceable_positions

    def _position_ids(self, image_grid_thw):
        # One image per call (the runtime's contract), as tensor ops only.
        merge = self.visual.spatial_merge_size
        t, h, w = image_grid_thw[0]
        hpos = torch.arange(h).unsqueeze(1).expand(-1, w)
        wpos = torch.arange(w).unsqueeze(0).expand(h, -1)
        hpos, wpos = (
            pos.reshape(h // merge, merge, w // merge, merge).permute(0, 2, 1, 3).flatten() for pos in (hpos, wpos)
        )
        return torch.stack([hpos, wpos], dim=-1).repeat(t, 1)

    def forward(self, pixel_values, image_grid_thw):
        kwargs = {"position_ids": self._position_ids(image_grid_thw)} if self.traceable_positions else {}
        output = self.visual(pixel_values, grid_thw=image_grid_thw, **kwargs)
        pooled = getattr(output, "pooler_output", None)
        return output if pooled is None else pooled


@contextlib.contextmanager
def _causal_sdpa():
    """Make transformers hand SDPA ``attn_mask=None, is_causal=True`` while tracing.

    Under ``torch.jit.trace`` transformers always materializes an S x S mask, so
    ``create_causal_mask`` is stubbed out for the trace. ``use_gqa_in_sdpa`` is
    pinned to False so K/V keep ``repeat_kv`` and SDPA stays rank 4; the rank-5
    GQA form is not lowered to the fused SDPA kernel on Intel GPU.
    """
    from transformers.integrations import sdpa_attention
    from transformers.models.qwen2_vl import modeling_qwen2_vl as qwen2_vl

    saved_mask = qwen2_vl.create_causal_mask
    saved_gqa = sdpa_attention.use_gqa_in_sdpa
    qwen2_vl.create_causal_mask = lambda **_kwargs: None
    sdpa_attention.use_gqa_in_sdpa = lambda *_args, **_kwargs: False
    try:
        yield
    finally:
        qwen2_vl.create_causal_mask = saved_mask
        sdpa_attention.use_gqa_in_sdpa = saved_gqa


@contextlib.contextmanager
def _mask_free_vision_attention():
    """Trace each ViT block as one full-sequence, mask-free SDPA.

    Qwen2-VL packs every image of a call into one sequence and restricts
    attention to each image's block via ``cu_seqlens``. The runtime calls the
    visual IR once per image, so there is a single block and dropping the mask is
    an identity; it also keeps the sequence dimension dynamic, which the
    upstream split path (``lengths.tolist()``) would bake in. Q/K/V go to
    ``[H, L, D]`` in one permute instead of a permute plus three transposes.
    """
    from transformers.models.qwen2_vl import modeling_qwen2_vl as qwen2_vl

    def forward(self, hidden_states, cu_seqlens, rotary_pos_emb=None, position_embeddings=None, **_kwargs):
        if len(cu_seqlens) != 2:
            raise RuntimeError(
                f"mask-free vision export needs a single-image example, got cu_seqlens of length {len(cu_seqlens)}"
            )
        seq_length = hidden_states.shape[-2]
        query_states, key_states, value_states = (
            self.qkv(hidden_states).reshape(seq_length, 3, self.num_heads, -1).permute(1, 2, 0, 3).unbind(0)
        )
        # apply_rotary_pos_emb_vision assumes [L, H, D]; same arithmetic on [H, L, D].
        cos, sin = position_embeddings
        original_dtype = query_states.dtype
        query_float, key_float = query_states.float(), key_states.float()
        cos_b, sin_b = cos.unsqueeze(0).float(), sin.unsqueeze(0).float()
        rotate_half = qwen2_vl.rotate_half
        query_states = ((query_float * cos_b) + (rotate_half(query_float) * sin_b)).to(original_dtype)
        key_states = ((key_float * cos_b) + (rotate_half(key_float) * sin_b)).to(original_dtype)
        attn_output = functional.scaled_dot_product_attention(
            query_states.unsqueeze(0),
            key_states.unsqueeze(0),
            value_states.unsqueeze(0),
            attn_mask=None,
            dropout_p=0.0,
            is_causal=False,
        )
        attn_output = attn_output.transpose(1, 2).reshape(seq_length, -1).contiguous()
        return self.proj(attn_output)

    saved = qwen2_vl.VisionAttention.forward
    qwen2_vl.VisionAttention.forward = forward
    try:
        yield
    finally:
        qwen2_vl.VisionAttention.forward = saved


def _processor(source: Path, min_image_tokens: int, max_image_tokens: int):
    from transformers import AutoProcessor

    processor = AutoProcessor.from_pretrained(
        str(source),
        min_pixels=min_image_tokens * IMAGE_FACTOR * IMAGE_FACTOR,
        max_pixels=max_image_tokens * IMAGE_FACTOR * IMAGE_FACTOR,
        use_fast=False,
    )
    processor.tokenizer.padding_side = "right"
    return processor


def _fused_example(processor, width: int, height: int) -> dict:
    """One synthetic image with a caption, the same shape of input the runtime builds."""
    pixels = np.random.default_rng(0).integers(0, 256, (height, width, 3), dtype=np.uint8)
    text = GmeOpenVINO._prompt("A photo of a cat sitting on a sofa.", has_image=True, instruction=DEFAULT_INSTRUCTION)
    return dict(
        processor(
            text=[text],
            images=[Image.fromarray(pixels)],
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
            return_tensors="pt",
        )
    )


def _load_visual_only(source: Path) -> torch.nn.Module:
    """Load just the vision tower's weights, skipping the 2B language model."""
    from safetensors import safe_open
    from transformers import AutoConfig
    from transformers.models.qwen2_vl.modeling_qwen2_vl import Qwen2VisionTransformerPretrainedModel

    config = AutoConfig.from_pretrained(str(source))
    visual = Qwen2VisionTransformerPretrainedModel._from_config(config.vision_config)
    weight_map = json.loads((source / "model.safetensors.index.json").read_text())["weight_map"]
    shards = sorted({shard for name, shard in weight_map.items() if name.startswith("visual.")})
    state_dict = {}
    for shard_name in shards:
        with safe_open(source / shard_name, framework="pt", device="cpu") as shard:
            for name in shard.keys():
                if name.startswith("visual."):
                    state_dict[name.removeprefix("visual.")] = shard.get_tensor(name)
    visual.load_state_dict(state_dict, strict=True)
    return visual.eval()


def _convert(module, example_inputs, path: Path, input_names, shapes, patch) -> None:
    logger.info("Converting GME %s", path.name)
    with patch():
        model = ov.convert_model(module, example_input=example_inputs)
    for port, name in zip(model.inputs, input_names, strict=True):
        port.get_tensor().set_names({name})
    model.outputs[0].get_tensor().set_names({"embedding"})
    model.reshape(dict(enumerate(shapes)))
    ov.save_model(model, str(path), compress_to_fp16=False)
    del model
    gc.collect()


def _compress_int8(source: Path, target: Path, ignored_patterns=()) -> None:
    import nncf

    logger.info("Compressing %s to INT8", source.name)
    kwargs = {"mode": nncf.CompressWeightsMode.INT8_ASYM}
    if ignored_patterns:
        kwargs["ignored_scope"] = nncf.IgnoredScope(patterns=list(ignored_patterns), validate=False)
    model = nncf.compress_weights(ov.Core().read_model(str(source)), **kwargs)
    ov.save_model(model, str(target))
    del model
    gc.collect()


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    left = left.reshape(-1).astype(np.float64)
    right = right.reshape(-1).astype(np.float64)
    return float(np.dot(left, right) / (np.linalg.norm(left) * np.linalg.norm(right)))


def _ov_embedding(package: Path, language_xml: str, visual_xml: str, inputs: dict, fp32_math: bool) -> np.ndarray:
    core = ov.Core()
    config = {ov.properties.hint.inference_precision: ov.Type.f32} if fp32_math else {}
    visual = core.compile_model(str(package / visual_xml), "CPU", config)
    image_embeds = visual({"pixel_values": inputs["pixel_values"].numpy(),
                           "image_grid_thw": inputs["image_grid_thw"].numpy()})[0]
    language = core.compile_model(str(package / language_xml), "CPU", config)
    return np.asarray(language({"input_ids": inputs["input_ids"].numpy(),
                                "attention_mask": inputs["attention_mask"].numpy(),
                                "image_embeds": np.asarray(image_embeds)})[0])


def resolve_checkpoint(hf_model_id: str, revision: Optional[str] = None) -> Path:
    """A local checkpoint directory, downloading from the Hugging Face Hub if needed."""
    if Path(hf_model_id).is_dir():
        return Path(hf_model_id)
    from huggingface_hub import snapshot_download

    logger.info("Downloading GME checkpoint %s", hf_model_id)
    return Path(snapshot_download(hf_model_id, revision=revision, allow_patterns=CHECKPOINT_PATTERNS))


def export_package(
    hf_model_id: str,
    output_dir: str | Path,
    weight_format: str = "int8",
    revision: Optional[str] = None,
) -> Path:
    """Export the GME package to ``output_dir`` and return it.

    The package is built in a sibling staging directory and renamed into place
    only once it has passed the reference check, so an interrupted export never
    leaves a directory that looks like a complete package.
    """
    if weight_format not in SUPPORTED_WEIGHT_FORMATS:
        raise ValueError(f"GME weight_format must be one of {SUPPORTED_WEIGHT_FORMATS}, got {weight_format!r}")
    output_dir = Path(output_dir)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    source = resolve_checkpoint(hf_model_id, revision)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=str(output_dir.parent)))
    try:
        _build_package(source, staging, weight_format, hf_model_id)
        staging.chmod(0o755)  # mkdtemp creates it owner-only
        staging.rename(output_dir)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    logger.info("GME OpenVINO package ready at %s", output_dir)
    return output_dir


def _build_package(source: Path, package: Path, weight_format: str, model_name: str) -> None:
    for name in PROCESSOR_ASSETS:
        if (source / name).is_file():
            shutil.copy2(source / name, package / name)

    # Trace at the minimum image size; the validation input uses a different one
    # so a shape baked into the graph would show up as a failure.
    trace_inputs = _fused_example(_processor(source, MIN_IMAGE_TOKENS, MIN_IMAGE_TOKENS), 448, 448)
    check_inputs = _fused_example(_processor(source, MIN_IMAGE_TOKENS, MAX_IMAGE_TOKENS), 700, 500)

    from transformers import AutoModelForImageTextToText

    logger.info("Loading GME checkpoint from %s", source)
    base = AutoModelForImageTextToText.from_pretrained(str(source), dtype=torch.float32).eval()
    hidden_size = base.config.get_text_config().hidden_size
    with torch.no_grad():
        visual_reference = GmeVisualEncoder(base.model.visual).eval()
        reference = GmeLanguageEmbed(base).eval()(
            check_inputs["input_ids"],
            check_inputs["attention_mask"],
            visual_reference(check_inputs["pixel_values"], check_inputs["image_grid_thw"]),
        ).numpy()
    image_tokens = int((trace_inputs["input_ids"] == base.config.image_token_id).sum())
    _convert(
        GmeLanguageEmbed(base, causal_attention=True).eval(),
        (trace_inputs["input_ids"], trace_inputs["attention_mask"], torch.zeros((image_tokens, hidden_size))),
        package / "gme_language_fp32.xml",
        ["input_ids", "attention_mask", "image_embeds"],
        [ov.PartialShape([-1, -1]), ov.PartialShape([-1, -1]), ov.PartialShape([-1, hidden_size])],
        _causal_sdpa,
    )
    del base, visual_reference
    gc.collect()

    _convert(
        GmeVisualEncoder(_load_visual_only(source), traceable_positions=True).eval(),
        (trace_inputs["pixel_values"], trace_inputs["image_grid_thw"]),
        package / "gme_visual_fp32.xml",
        ["pixel_values", "image_grid_thw"],
        [ov.PartialShape([-1, trace_inputs["pixel_values"].shape[-1]]), ov.PartialShape([-1, 3])],
        _mask_free_vision_attention,
    )
    gc.collect()

    language_xml, visual_xml = f"gme_language_{weight_format}.xml", f"gme_visual_{weight_format}.xml"
    if weight_format == "int8":
        _compress_int8(package / "gme_language_fp32.xml", package / language_xml)
        # Quantizing the ViT rotary frequencies collapses the image embedding.
        _compress_int8(package / "gme_visual_fp32.xml", package / visual_xml, ignored_patterns=[".*rotary.*"])
        for name in ("gme_language_fp32", "gme_visual_fp32"):
            for suffix in (".xml", ".bin"):
                (package / f"{name}{suffix}").unlink()

    cosine = _cosine(
        _ov_embedding(package, language_xml, visual_xml, check_inputs, fp32_math=weight_format == "fp32"),
        reference,
    )
    logger.info("GME %s export vs PyTorch: cosine=%.6f", weight_format, cosine)
    if cosine < MIN_REFERENCE_COSINE[weight_format]:
        raise RuntimeError(
            f"GME {weight_format} export differs from the PyTorch model (cosine {cosine:.6f} < "
            f"{MIN_REFERENCE_COSINE[weight_format]}); the installed transformers version may not be supported"
        )

    config = {
        "format": 1,
        "model": model_name,
        "embedding_dim": hidden_size,
        "pooling": "last valid token, L2 normalized",
        "language_model": language_xml,
        "visual_model": visual_xml,
        "processor": {
            "min_image_tokens": MIN_IMAGE_TOKENS,
            "max_image_tokens": MAX_IMAGE_TOKENS,
            "max_length": MAX_LENGTH,
            "padding_side": "right",
        },
        "precisions": {weight_format: {"language": language_xml, "visual": visual_xml}},
        "default_precision": weight_format,
        "reference_cosine": cosine,
    }
    (package / "gme_openvino_config.json").write_text(json.dumps(config, indent=2) + "\n")
