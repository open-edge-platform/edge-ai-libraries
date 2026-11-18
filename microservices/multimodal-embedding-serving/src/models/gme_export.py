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
(causal SDPA for the decoder, mask-free head-first SDPA for the vision tower,
rank-3 ``[1, L, C]`` vision projections). Weights are then compressed to
``weight_format`` and the result is checked against the PyTorch model before
the package is published.
"""

from __future__ import annotations

import contextlib
import gc
import json
import os
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

SUPPORTED_WEIGHT_FORMATS = ("fp32", "int8", "int4")
# The precision is chosen with GME_PRECISION, by the service and by
# scripts/export_gme_ov.py alike.
PRECISION_ENV = "GME_PRECISION"
DEFAULT_PRECISION = "int8"


def resolve_precision(value: Optional[str] = None) -> str:
    """The GME precision to use: ``value``, else ``$GME_PRECISION``, else INT8."""
    precision = (value or os.getenv(PRECISION_ENV) or DEFAULT_PRECISION).strip().lower()
    if precision not in SUPPORTED_WEIGHT_FORMATS:
        raise ValueError(f"{PRECISION_ENV} must be one of {SUPPORTED_WEIGHT_FORMATS}, got {precision!r}")
    return precision


def package_dir_name(base: str, precision: str) -> str:
    """Directory of a precision's package; INT8 keeps the unsuffixed name it always had."""
    return base if precision == DEFAULT_PRECISION else f"{base}-{precision}"
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
# on images and 0.998 on fused inputs, INT4 0.94-0.96 on every input type; a
# broken trace lands far below either.
MIN_REFERENCE_COSINE = {"fp32": 0.9999, "int8": 0.99, "int4": 0.90}
# Calibration prompts for the language IR's INT4 compression. Plain data-free
# INT4 hurts text embeddings much more than image/fused ones (last-token pooling
# over a decoder is sensitive to per-channel weight error), so AWQ + scale
# estimation search scales over representative activations. Diversity of
# length, language and register matters more than domain here. Pairs are
# (text, instruction); None is the document-side default instruction.
INT4_CALIBRATION_TEXTS: list[tuple[str, Optional[str]]] = [
    ("How do I reset my password on this website?", None),
    ("What time does the museum open on Sundays?", None),
    ("The quarterly earnings report showed a 12% increase in revenue year over year.", None),
    ("Mix 2 cups of flour with a teaspoon of baking soda, then fold in the melted butter.", None),
    ("def fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)", None),
    ("SELECT customer_id, SUM(total) FROM orders GROUP BY customer_id ORDER BY 2 DESC LIMIT 10;", None),
    ("A large orange cat sleeping on a windowsill in the afternoon sun.", None),
    ("The Amazon rainforest produces roughly 20% of the world's oxygen supply.", None),
    ("请解释一下什么是卷积神经网络，以及它在图像识别中的应用。", None),
    ("北京的秋天天气凉爽，是登长城的最佳季节之一。", None),
    ("Photosynthesis converts carbon dioxide and water into glucose and oxygen using light energy.", None),
    ("On 2024-03-14 at 09:30 UTC, flight AC142 departed gate B17 for a 6h45m transatlantic crossing.", None),
    (
        "Neural network quantization reduces model size and inference latency by representing "
        "weights and activations with fewer bits, typically 8-bit integers instead of 32-bit "
        "floating point, at the cost of some accuracy that can often be recovered with "
        "calibration-aware or quantization-aware training techniques.",
        None,
    ),
    (
        "The French Revolution, beginning in 1789, fundamentally transformed French society by "
        "abolishing the monarchy and feudal privileges, establishing in their place a series of "
        "republics and empires whose legal and political innovations reverberated across Europe "
        "for the following century.",
        None,
    ),
    ("Battery electric vehicles convert over 77% of electrical energy from the grid to power at the wheels.", None),
    ("The train to Boston leaves platform 4 at quarter past six every weekday morning.", None),
    ("import numpy as np\narr = np.zeros((3, 3), dtype=np.float32)\narr[1, 1] = 1.0", None),
    ("A weathered wooden pier extending into a calm lake at sunrise, mist rising off the water.", None),
    ("Interest rates rose by 25 basis points, the third consecutive increase this fiscal year.", None),
    ("为什么天空是蓝色的？这与太阳光在大气层中的瑞利散射有关。", None),
    ("Please summarize the key differences between TCP and UDP for a networking course.", None),
    ("A red mountain bike leaning against a brick wall in an alleyway.", None),
    ("The recipe calls for simmering the sauce on low heat for at least forty-five minutes.", None),
    ("Global smartphone shipments declined 3.2% in the first quarter compared to the prior year.", None),
    ("192.168.1.1 is a commonly used private IPv4 address for home network routers.", None),
    ("Can you recommend a good beginner book on machine learning?", None),
    (
        "In distributed systems, the CAP theorem states that a system can provide at most two of "
        "the following three guarantees simultaneously: consistency, availability, and partition "
        "tolerance, which forces architects to make explicit tradeoffs depending on workload.",
        None,
    ),
    ("A stack of pancakes topped with maple syrup and a pat of melting butter.", None),
    ("水的沸点在标准大气压下是攝氏一百度。", None),
    ("What kind of car is this?", "Find an image that matches the given text."),
    ("best hiking trails near Denver with waterfalls", "Represent this sentence for searching relevant passages."),
    ("How does gradient descent converge for a convex loss function?", "Find a passage that answers this question."),
]


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

    The block stack runs on ``[1, L, C]`` instead of ``[L, C]`` (a singleton
    axis, not a batch). The values are identical, but the GPU plugin selects
    kernels by rank: the INT4 weight reorder in the GME GPU-plugin patch set
    (opt-3) only takes rank-3 inputs, and on a stock plugin the two ranks run
    at the same speed with bit-identical outputs.
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
        # Straight to [1, L, C]: keeps `proj` rank 3 without a separate Unsqueeze.
        attn_output = attn_output.transpose(1, 2).reshape(1, seq_length, -1).contiguous()
        return self.proj(attn_output)

    def tower_forward(self, hidden_states, grid_thw, **kwargs):
        # Upstream's forward, with the block stack on [1, L, C]. VisionMlp and the
        # residual adds are shape-agnostic and the attention above reads shape[-2];
        # the merger gets [L, C] back, as upstream.
        position_ids = qwen2_vl.get_vision_position_ids(grid_thw, self.spatial_merge_size, kwargs=kwargs)
        cu_seqlens = qwen2_vl.get_vision_cu_seqlens(grid_thw, kwargs=kwargs)
        hidden_states = self.patch_embed(hidden_states)
        rotary_pos_emb = self.rotary_pos_emb(position_ids)
        emb = torch.cat((rotary_pos_emb, rotary_pos_emb), dim=-1)
        position_embeddings = (emb.cos(), emb.sin())
        hidden_states = hidden_states.unsqueeze(0)
        for blk in self.blocks:
            hidden_states = blk(hidden_states, cu_seqlens=cu_seqlens, position_embeddings=position_embeddings)
        hidden_states = hidden_states.squeeze(0)
        return qwen2_vl.BaseModelOutputWithPooling(
            last_hidden_state=hidden_states,
            pooler_output=self.merger(hidden_states),
        )

    saved = qwen2_vl.VisionAttention.forward
    saved_tower = qwen2_vl.Qwen2VisionTransformerPretrainedModel.forward
    qwen2_vl.VisionAttention.forward = forward
    qwen2_vl.Qwen2VisionTransformerPretrainedModel.forward = tower_forward
    try:
        yield
    finally:
        qwen2_vl.VisionAttention.forward = saved
        qwen2_vl.Qwen2VisionTransformerPretrainedModel.forward = saved_tower


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


def _compress(source: Path, target: Path, weight_format: str, **kwargs) -> None:
    import nncf

    logger.info("Compressing %s to %s", source.name, weight_format.upper())
    model = nncf.compress_weights(ov.Core().read_model(str(source)), **kwargs)
    ov.save_model(model, str(target))
    del model
    gc.collect()


def _calibration_dataset(tokenizer, hidden_size: int):
    """INT4 calibration inputs for the language IR, one ``[1, S]`` text-only sample each.

    Each prompt is tokenized on its own, as the runtime invokes the language IR
    per sample, so calibration sees real sequence lengths rather than one padded
    shape. ``image_embeds`` is the empty tensor text-only inference feeds.
    """
    import nncf

    prompts = [
        GmeOpenVINO._prompt(text, has_image=False, instruction=instruction or DEFAULT_INSTRUCTION)
        for text, instruction in INT4_CALIBRATION_TEXTS
    ]

    def transform(prompt: str) -> dict:
        encoded = tokenizer([prompt], truncation=True, max_length=MAX_LENGTH, return_tensors="np")
        return {
            "input_ids": encoded["input_ids"],
            "attention_mask": encoded["attention_mask"],
            "image_embeds": np.empty((0, hidden_size), dtype=np.float32),
        }

    return nncf.Dataset(prompts, transform)


def _compression_kwargs(weight_format: str, tokenizer, hidden_size: int) -> tuple[dict, dict]:
    """NNCF ``compress_weights`` arguments for the language and visual IRs."""
    import nncf
    from nncf.quantization.advanced_parameters import AdvancedCompressionParameters, GroupSizeFallbackMode

    # Quantizing the ViT rotary frequencies collapses the image embedding.
    rotary = nncf.IgnoredScope(patterns=[".*rotary.*"], validate=False)
    if weight_format == "int8":
        mode = nncf.CompressWeightsMode.INT8_ASYM
        return {"mode": mode}, {"mode": mode, "ignored_scope": rotary}
    int4 = {"mode": nncf.CompressWeightsMode.INT4_ASYM, "group_size": 128, "ratio": 1.0}
    language = {
        **int4,
        "dataset": _calibration_dataset(tokenizer, hidden_size),
        "awq": True,
        "scale_estimation": True,
        "subset_size": len(INT4_CALIBRATION_TEXTS),
    }
    # The vision tower does not show the decoder's INT4 sensitivity, so it stays
    # data-free; ADJUST shrinks the group for the few matmuls whose channel count
    # is not a multiple of 128 instead of failing.
    visual = {
        **int4,
        "ignored_scope": rotary,
        "advanced_parameters": AdvancedCompressionParameters(group_size_fallback_mode=GroupSizeFallbackMode.ADJUST),
    }
    return language, visual


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
    if weight_format != "fp32":
        tokenizer = _processor(source, MIN_IMAGE_TOKENS, MAX_IMAGE_TOKENS).tokenizer
        language_kwargs, visual_kwargs = _compression_kwargs(weight_format, tokenizer, hidden_size)
        _compress(package / "gme_language_fp32.xml", package / language_xml, weight_format, **language_kwargs)
        _compress(package / "gme_visual_fp32.xml", package / visual_xml, weight_format, **visual_kwargs)
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
