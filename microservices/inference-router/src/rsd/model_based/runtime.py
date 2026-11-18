# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Backbone runtime: the compiled OpenVINO backbone shared by all classifiers.

A :class:`BackboneRuntime` holds the compiled tokenizer / text_embeddings /
language_model of one backbone on one device and exposes the post-norm last
hidden state. It is compiled once per ``(ir_dir, device)`` (see
:func:`get_runtime`) and shared by every classifier on that backbone; a
classifier on top is just a prompt plus a small head.

This is the only module that imports ``openvino``.

IR layouts accepted (the differences are detected from the IR, not configured):

* **router contract** -- ``openvino_language_model.xml`` already outputs
  ``last_hidden_state`` (post final norm) and takes ``inputs_embeds``.
* **split VLM export** (Qwen3.5) -- ``openvino_language_model.xml`` outputs vocab
  ``logits``; the lm_head MatMul's input is exposed as ``last_hidden_state`` in
  memory and the lm_head is pruned.
* **single-graph export** (Qwen3) -- ``openvino_model.xml`` with ``input_ids``;
  the token-embedding Gather is split out into its own model, then the hidden
  state is exposed as above.

``position_ids`` layout (mRoPE ``[4, 1, L]`` vs ``[1, L]``) and statefulness
(``beam_idx`` + ``reset_state``) are read off the language model.

The hard classifier's head rows are read from the lm_head weight whenever the
IR has one (the pruned lm_head of a logits export, or ``openvino_lm_head.xml``).
Tied embeddings are only a fallback: on weight-compressed IRs (INT8 / INT4) the
lm_head and the embedding table are quantized separately, and using the
embedding rows flips a few percent of decisions.

**Token-form runtimes** (``token_patch=...``) write a soft version's soft-prompt
and class rows into the vocabulary constants (see :mod:`.vocab_tokens`):
every free-row table behind the embedding Gather and the lm_head MatMul gets
the same rows, and the full lm_head is kept -- fed the last position only --
so one compiled model outputs the vocabulary ``logits [1, V]`` (the classifier
reads its class tokens out of them by id) and ``last_hidden_state``. Each
distinct patch is a distinct compiled model, keyed by its digest. FP16/BF16
IRs only (weight-compressed constants cannot be written; such an IR cannot
host soft versions) and only exports with an in-graph lm_head. Hard versions
and multi-class rules run on any runtime of the backbone, a patched one
included, since the patch touches only free rows.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional, Sequence, Tuple
from weakref import WeakValueDictionary

import numpy as np

from src.rsd.model_based.vocab_tokens import VocabTokenPatch

logger = logging.getLogger(__name__)

HIDDEN_NAME = "last_hidden_state"
LOGITS_NAME = "logits"
TOKENIZER_XML = "openvino_tokenizer.xml"
TEXT_EMBEDDINGS_XML = "openvino_text_embeddings_model.xml"
LANGUAGE_MODEL_XML = "openvino_language_model.xml"
SINGLE_GRAPH_XML = "openvino_model.xml"
LM_HEAD_XML = "openvino_lm_head.xml"


def _import_openvino():
    try:
        import openvino as ov
        import openvino_tokenizers  # noqa: F401  (registers the tokenizer op extension)
    except ImportError as exc:  # pragma: no cover - env dependent
        raise ImportError(
            "BackboneRuntime needs the OpenVINO runtime deps "
            "(openvino, openvino-tokenizers, numpy); they ship with "
            "inference-router's [ov] dependencies -- reinstall the project."
        ) from exc
    return ov


def resolve_device(device: str) -> str:
    """Fall back to CPU when a requested GPU isn't actually available."""
    if not device or not device.upper().startswith("GPU"):
        return device
    try:
        from openvino import Core

        available = Core().available_devices
    except Exception as exc:
        logger.warning(
            "Could not enumerate OpenVINO devices (%s); trying %r as requested",
            exc,
            device,
        )
        return device

    available_ok = device in available or (
        "." not in device and any(d.split(".", 1)[0] == "GPU" for d in available)
    )
    if available_ok:
        return device

    logger.warning(
        "Requested device %r not available (have %s); falling back to CPU",
        device,
        available,
    )
    return "CPU"


# -- in-memory graph adaptation -----------------------------------------------


def _lm_head_matmul(model, by_name: bool = True):
    results = model.get_results()
    if len(results) != 1:
        raise ValueError(f"expected a single logits Result, got {len(results)}")
    node = results[0].input_value(0).get_node()
    if node.get_type_name() != "MatMul" or (by_name and "lm_head" not in node.get_friendly_name()):
        raise ValueError(f"Result is not fed by the lm_head MatMul: {node.get_friendly_name()}")
    return node


def _head_rows_model(matmul):
    """``ids [n] -> lm_head weight rows [n, H]``, sharing the lm_head's weight subgraph.

    The Gather sits on the (possibly compressed) weight, so compiling it on CPU
    does not decompress the whole vocab table.
    """
    import openvino as ov
    from openvino import opset13 as ops

    transpose_b = matmul.get_attributes()["transpose_b"]
    ids = ops.parameter(ov.PartialShape([-1]), ov.Type.i64, name="ids")
    rows = ops.gather(matmul.input_value(1), ids, np.array(0 if transpose_b else 1))
    if not transpose_b:  # weight is [H, V]: gathered columns -> rows
        rows = ops.transpose(rows, np.array([1, 0]))
    return ov.Model([ops.result(rows)], [ids], "lm_head_rows")


def _expose_hidden(model):
    """Replace the ``logits`` Result with the lm_head input (post-norm hidden)."""
    from openvino import opset13 as ops

    matmul = _lm_head_matmul(model)
    hidden = ops.result(matmul.input_value(0))
    hidden.output(0).get_tensor().set_names({HIDDEN_NAME})
    logits = model.get_results()[0]
    model.add_results([hidden])
    model.remove_result(logits)
    model.validate_nodes_and_infer_types()
    return model


def _mask_linear_attention(model) -> int:
    """Zero masked positions at the input of every linear-attention (GDN) layer.

    HuggingFace's Qwen3.5 gated-delta-net layers multiply their input by the
    attention mask (``apply_mask_to_padding_states``) -- but only for batches of
    two or more, so the trace behind the export drops it and the exported
    layers ignore ``attention_mask``. The soft prompts were trained and evaluated
    in batches, where the pad block between soft prompt and query is zeroed
    there; at batch size 1 the pads would feed the recurrent state instead and
    the 2B default version loses ~7 points of route accuracy. With an all-ones
    mask the multiply is a no-op. Returns the number of layers patched.
    """
    from openvino import opset13 as ops

    projections = [
        op
        for op in model.get_ordered_ops()
        if op.get_type_name() == "MatMul"
        and "linear_attn.in_proj_qkv" in op.get_friendly_name()
    ]
    if not projections:
        return 0
    mask = model.input("attention_mask")
    for qkv in projections:
        hidden = qkv.input_value(0)
        weights = ops.unsqueeze(ops.convert(mask, hidden.get_element_type()), np.array([-1]))
        masked = ops.multiply(hidden, weights)
        for target in list(hidden.get_target_inputs()):
            node = target.get_node()
            name = node.get_friendly_name()
            if node.get_type_name() == "MatMul" and "linear_attn.in_proj" in name:
                target.replace_source_output(masked.output(0))
    model.validate_nodes_and_infer_types()
    return len(projections)


def _embedding_gather(model):
    for op in model.get_ordered_ops():
        if op.get_type_name() == "Gather" and "embed_tokens" in op.get_friendly_name():
            return op
    raise ValueError("token-embedding Gather (embed_tokens) not found")


def _input_ids_param(model):
    return next(p for p in model.get_parameters() if "input_ids" in p.output(0).get_names())


def _split_embedding(core, xml: str):
    """Split a single-graph IR into ``(text_embeddings, language_model)`` models."""
    import openvino as ov
    from openvino import opset13 as ops

    emb_model = core.read_model(xml)
    gather = _embedding_gather(emb_model)
    emb_model = ov.Model(
        [ops.result(gather.output(0))], [_input_ids_param(emb_model)], "text_embeddings"
    )

    lm = core.read_model(xml)
    gather = _embedding_gather(lm)
    hidden = gather.get_output_partial_shape(0)[-1]
    embeds = ops.parameter(ov.PartialShape([-1, -1, hidden]), ov.Type.f32, name="inputs_embeds")
    gather.output(0).replace(embeds.output(0))
    # replace() merges the old Gather output's tensor names in; reset to the contract name.
    embeds.output(0).get_tensor().set_names({"inputs_embeds"})
    ids = _input_ids_param(lm)
    # The remaining input_ids consumers only read [batch, seq]: take it from inputs_embeds.
    live = {op.get_friendly_name() for op in lm.get_ordered_ops()}
    for target in list(ids.output(0).get_target_inputs()):
        node = target.get_node()
        if node.get_friendly_name() not in live:
            continue  # the Convert that fed the old Gather; now dead
        if node.get_type_name() != "ShapeOf":
            raise ValueError(f"unexpected input_ids consumer {node.get_type_name()}")
        dims = ops.slice(
            ops.shape_of(embeds, node.get_output_element_type(0)),
            np.array([0]),
            np.array([2]),
            np.array([1]),
        )
        node.output(0).replace(dims.output(0))
    lm.remove_parameter(ids)
    lm.add_parameters([embeds])
    lm.validate_nodes_and_infer_types()
    return emb_model, lm


def _chat_style(ir_dir: Path) -> str:
    """How hard prompts are rendered for this backbone: ``"qwen"`` or ``"llama3"``.

    Read from the exported ``config.json``'s ``model_type`` -- ``llama`` uses
    Llama-3's ``<|start_header_id|>`` template, everything else the Qwen
    ``<|im_start|>`` one. Unknown config falls back to Qwen.
    """
    try:
        config = json.loads((ir_dir / "config.json").read_text())
    except (OSError, ValueError):
        return "qwen"
    model_type = str(config.get("model_type", config.get("text_config", {}).get("model_type", "")))
    return "llama3" if model_type == "llama" else "qwen"


def _tied_embeddings(ir_dir: Path) -> bool:
    """``tie_word_embeddings`` from ``config.json`` (VLMs nest it under ``text_config``)."""
    try:
        config = json.loads((ir_dir / "config.json").read_text())
    except (OSError, ValueError):
        return True  # no config: assume tied (true for all shipped backbones)
    text_config = config.get("text_config", {})
    return bool(text_config.get("tie_word_embeddings", config.get("tie_word_embeddings", True)))


# -- vocabulary-row patching (token-form runtimes) -------------------------------


class TokenFormError(ValueError):
    """The IR cannot host a token-form version (compressed weights, no in-graph lm_head)."""


def _backing_constant(output):
    """``(constant, port)`` behind an Input port / Output through Converts.

    ``port`` is always an input port that directly feeds from the constant --
    the given one when the consumer reads the constant without a Convert in
    between, else the Convert's own input -- which is where a replacement
    constant or an in-graph scatter must be spliced in, so any Convert between
    the constant and the original consumer keeps running. An Output argument
    has no single consumer, so its ``port`` is ``None`` (callers that only
    identify the constant still work). ``None`` (whole call) when decompressed:
    weight compression stores u8/i8 plus scale / zero-point nodes, so anything
    but a chain of Converts over a Constant means the table cannot be written.
    """
    port = output if hasattr(output, "get_source_output") else None
    source = port.get_source_output() if port is not None else output
    node = source.get_node()
    for _ in range(4):
        kind = node.get_type_name()
        if kind == "Constant":
            return node, port
        if kind == "Convert":
            port = node.input(0)
            node = port.get_source_output().get_node()
            continue
        return None
    return None


def _read_output_f32(core, output) -> np.ndarray:
    """Exact float32 values of a constant-table output, read through a throwaway graph.

    ``Constant.get_data()`` misreports bf16 constants in this OpenVINO build,
    so the table is read by compiling a one-Result graph that outputs it.
    bf16/f16 -> f32 is exact, so untouched rows keep their values bit-exactly.
    """
    ov = _import_openvino()
    from openvino import opset13 as ops

    if output.get_element_type() != ov.Type.f32:
        output = ops.convert(output, ov.Type.f32).output(0)
    readout = ov.Model([ops.result(output)], [])
    request = core.compile_model(readout, "CPU").create_infer_request()
    values = np.asarray(request.infer([])[0], dtype=np.float32)  # already f32: a view, no copy
    return values if values.flags.writeable else values.copy()


def _write_rows(core, node, rows_by_id: dict, *, columns: bool, target_rows: Optional[int] = None) -> None:
    """Rebuild the table constant with the given rows replaced.

    f16 and f32 tables are rebuilt in their own dtype: ``get_data`` reports
    them correctly and a same-dtype ``ops.constant`` is a memcpy. A bf16 table
    is replaced with an **f32** constant instead -- equal in value, because
    bf16 -> f32 is exact and the graph's own Convert produced precisely these
    numbers for the untouched rows, while the written rows even gain precision
    (no bf16 rounding). Two things rule out keeping the table bf16: the Python
    API cannot build a bf16 constant from raw bits, and both ways around it
    are broken on this OpenVINO build -- ``ops.constant(values, bf16)``
    converts 500M elements in a single-threaded loop (~11 s per table), and
    ConstantFolding over a ScatterND executes bf16 wrongly (an all-1.0 table
    folds to garbage). Costs one extra table of memory.

    Ids past the table's end (a backbone without free rows -- llama3-1b)
    resize the rebuilt constant: rows are appended so the highest id fits.
    The appended rows the version does not write stay zero and are never
    addressed.
    """
    from openvino import opset13 as ops

    def _grow(values: np.ndarray) -> np.ndarray:
        axis = 1 if columns else 0  # the vocabulary dimension
        highest = max(max(rows_by_id) + 1, target_rows or 0)
        if highest <= values.shape[axis]:
            return values
        pad = [(0, 0), (0, 0)]
        pad[axis] = (0, highest - values.shape[axis])
        return np.pad(values, pad, constant_values=0)

    etype = node.get_element_type()
    if etype == _import_openvino().Type.f16:  # get_data reports f16 correctly
        values = _grow(np.array(node.get_data(), dtype=np.float16))  # writable copy
        for idx, row in rows_by_id.items():
            rounded = np.asarray(row, dtype=np.float32).astype(np.float16)  # RNE
            if columns:  # weight [H, V]: the vocabulary dimension is the columns
                values[:, idx] = rounded
            else:
                values[idx] = rounded
    else:  # f32 (or bf16, read exactly through the graph): keep the values
        values = _grow(_read_output_f32(core, node.output(0)))
        for idx, row in rows_by_id.items():
            if columns:
                values[:, idx] = row
            else:
                values[idx] = row
    replacement = ops.constant(values, values.dtype.type)
    replacement.set_friendly_name(node.get_friendly_name())
    for target_input in list(node.output(0).get_target_inputs()):
        target_input.replace_source_output(replacement.output(0))


def _patch_table_rows(core, output, rows_by_id, what: str, *, columns: bool = False, target_rows: Optional[int] = None) -> None:
    """Overwrite vocabulary rows of the table / weight behind ``output``.

    ``output`` is a weight input of the graph (a Gather's table or a MatMul's
    weight): a Constant or a Convert over one. Untouched rows keep their
    values bit-exactly; the written rows are stored at f16/f32 precision, and
    a bf16 table is replaced by an equal-valued f32 constant (see
    :func:`_write_rows`).

    Weight-compressed IRs (u8/i8 plus scale / zero-point) are rejected: rows
    cannot be written into them.
    """
    ov = _import_openvino()

    found = _backing_constant(output)
    if found is None:
        raise TokenFormError(
            f"{what} is weight-compressed (or not a plain constant); "
            "token-form versions need FP16/BF16 IRs"
        )
    node, const_port = found
    dtype = node.get_element_type()
    if dtype not in (ov.Type.f32, ov.Type.f16, ov.Type.bf16):
        raise TokenFormError(
            f"{what} is stored as {dtype}; token-form versions need FP16/BF16 IRs"
        )
    _write_rows(core, node, rows_by_id, columns=columns, target_rows=target_rows)
    # The write must have landed as a different constant holding the same
    # values at f16/f32 precision (the written values themselves are read
    # back by the token-form check in validate.py).
    written = _backing_constant(output)
    ok = (
        written is not None
        and written[0] is not node
        and written[0].get_element_type()
        in ((ov.Type.f32, ov.Type.f16) if dtype == ov.Type.bf16 else (dtype,))
    )
    if not ok:
        raise TokenFormError(
            f"writing rows into {what} did not produce a new patched constant"
        )


def _embedding_table_input(model):
    """The embedding-table input port (a Constant, or a Convert over one).

    Follows the ``embed_tokens`` Gather name when there is one (single-graph
    exports); otherwise accepts a model with exactly one Gather over a 2-D
    constant (the split ``text_embeddings`` export names its ops differently).
    The port is what row patching rewires; :func:`_backing_constant` reads the
    Constant behind it.
    """
    named, candidates = None, []
    for op in model.get_ordered_ops():
        if op.get_type_name() != "Gather":
            continue
        if "embed_tokens" in op.get_friendly_name():
            named = op
            break
        found = _backing_constant(op.input_value(0))
        rank = found[0].get_output_partial_shape(0).rank if found is not None else None
        if rank is not None and rank.is_static and rank.get_length() == 2:
            candidates.append(op)
    gather = named or (candidates[0] if len(candidates) == 1 else None)
    if gather is None:
        raise TokenFormError("no plain embedding table found; cannot write vocabulary rows")
    return gather.input(0)


def _keep_last_logits(model):
    """Keep the full lm_head but feed it only the last position; output logits and hidden.

    The vocabulary projection stays as exported (``logits [N, V]``) -- the
    token-form classifier reads its class tokens out of it by id
    (:meth:`BackboneRuntime.class_logits`) -- but runs on ``[N, H]`` instead
    of ``[N, L, H]``: without that, a 2000-token query would materialize
    ~2 GB of logits. The post-norm hidden stays available as an extra output
    (L3 fingerprints, hard versions sharing the runtime).
    """
    from openvino import opset13 as ops

    matmul = _lm_head_matmul(model)
    hidden = matmul.input_value(0)  # [N, L, H], post final norm
    seq_len = ops.gather(
        ops.shape_of(hidden, _import_openvino().Type.i64),
        np.array([1], np.int64),
        np.array(0, np.int64),
    )
    last_index = ops.subtract(ops.squeeze(seq_len, np.array([0], np.int64)), np.int64(1))
    last_hidden = ops.gather(hidden, last_index, np.array(1, np.int64))  # [N, H]
    matmul.input(0).replace_source_output(last_hidden.output(0))
    logits_result = ops.result(matmul.output(0))  # [N, V]
    logits_result.output(0).get_tensor().set_names({LOGITS_NAME})
    hidden_result = ops.result(hidden)
    hidden_result.output(0).get_tensor().set_names({HIDDEN_NAME})
    full_logits = model.get_results()[0]
    model.add_results([logits_result, hidden_result])
    model.remove_result(full_logits)
    model.validate_nodes_and_infer_types()
    return model


# -- runtime -------------------------------------------------------------------


class Tokenizer:
    """The IR's tokenizer alone, compiled on CPU.

    Enough to check a version's token ids (L2) without compiling the backbone.

    Args:
        ir_dir: OpenVINO IR directory holding ``openvino_tokenizer.xml``.
        core: OpenVINO ``Core`` to compile with (a new one by default).
    """

    def __init__(self, ir_dir: str, core: Any = None) -> None:
        core = core if core is not None else _import_openvino().Core()
        self._tok = core.compile_model(str(Path(ir_dir) / TOKENIZER_XML), "CPU")
        self._ids_port = self._find_ids_port(self._tok)

    @staticmethod
    def _find_ids_port(tok):
        for port in tok.outputs:
            if "input_ids" in port.get_names():
                return port
        for port in tok.outputs:  # fallback: first integer output
            if "int" in str(port.get_element_type()):
                return port
        raise ValueError("tokenizer has no input_ids output")

    def encode(self, text: str) -> np.ndarray:
        """Tokenize ``text`` to a 1-D int64 id array."""
        out = self._tok.create_infer_request().infer([np.array([text])])
        return out[self._ids_port][0].astype(np.int64)


class BackboneRuntime:
    """One backbone compiled on one device; shared by hard and soft classifiers.

    Thread-safe: every call runs on its own infer request, so a version can be
    validated and warmed up on the same backbone while requests are served.

    Args:
        ir_dir: OpenVINO IR directory (any layout in the module docstring).
        device: OpenVINO device string, e.g. ``"CPU"`` or ``"GPU.1"``; an
            unavailable GPU falls back to CPU (see :attr:`device`).
        token_patch: Rows to write into the vocabulary constants
            (:class:`~.vocab_tokens.VocabTokenPatch`, see the module docstring).
            Builds a token-form runtime: the full lm_head is kept (last position
            only) and :meth:`last_logits` / :meth:`class_logits` become
            available. Each distinct patch is a distinct compiled model.
    """

    def __init__(
        self,
        ir_dir: str,
        device: str = "CPU",
        token_patch: Optional[VocabTokenPatch] = None,
    ) -> None:
        ov = _import_openvino()
        self.ir_dir = str(ir_dir)
        self.requested_device = device
        self.device = resolve_device(device)
        self.token_patch_digest = token_patch.digest if token_patch is not None else None
        root = Path(ir_dir)

        core = ov.Core()
        # The tokenizer is a tiny graph; keep it on CPU regardless of the LM device.
        self.tokenizer = Tokenizer(ir_dir, core)
        # Prefix the tokenizer adds to every encoding (Llama's BOS; empty for
        # Qwen) -- not part of single-token answer codes (see strip_prompt_prefix).
        self._bos_prefix = self.tokenizer.encode("")

        if (root / LANGUAGE_MODEL_XML).exists():
            emb = core.read_model(str(root / TEXT_EMBEDDINGS_XML))
            lm = core.read_model(str(root / LANGUAGE_MODEL_XML))
        elif (root / SINGLE_GRAPH_XML).exists():
            emb, lm = _split_embedding(core, str(root / SINGLE_GRAPH_XML))
        else:
            raise FileNotFoundError(
                f"{ir_dir}: no {LANGUAGE_MODEL_XML} or {SINGLE_GRAPH_XML} -- not an OpenVINO LLM IR"
            )
        self.surgery = not any(HIDDEN_NAME in o.get_names() for o in lm.outputs)
        if token_patch is not None:
            if not self.surgery:
                raise TokenFormError(
                    f"{ir_dir}: the language model has no in-graph lm_head (router-contract "
                    "or separate-lm_head export); token-form versions need the "
                    "original export with vocab logits"
                )
            rows = token_patch.rows_by_id
            _patch_table_rows(core, _embedding_table_input(emb), rows, "the embedding table")
            matmul = _lm_head_matmul(lm)
            _patch_table_rows(
                core,
                matmul.input(1),
                rows,
                "the lm_head weight",
                columns=not matmul.get_attributes()["transpose_b"],
            )
            head_rows = _head_rows_model(matmul)
            lm = _keep_last_logits(lm)
        elif self.surgery:
            head_rows = _head_rows_model(_lm_head_matmul(lm))  # before the lm_head is pruned
            lm = _expose_hidden(lm)
        elif (root / LM_HEAD_XML).exists():
            head_rows = _head_rows_model(
                _lm_head_matmul(core.read_model(str(root / LM_HEAD_XML)), by_name=False)
            )
        else:
            head_rows = None

        self.token_form = token_patch is not None
        self._class_ids = (
            np.asarray(token_patch.label_ids, dtype=np.int64) if token_patch is not None else None
        )
        self.masked_linear_attention_layers = _mask_linear_attention(lm)
        self.hidden_size = lm.input("inputs_embeds").get_partial_shape()[-1].get_length()
        self.pos_rank = lm.input("position_ids").get_partial_shape().rank.get_length()
        self.stateful = len(lm.get_sinks()) > 0
        self._has_beam = any("beam_idx" in i.get_names() for i in lm.inputs)
        self.tied = _tied_embeddings(root)
        self.chat_style = _chat_style(root)  # how hard prompts are rendered
        self.head_source = (
            "lm_head" if head_rows is not None else "embeddings" if self.tied else None
        )
        # Head rows are read once per classifier build; tiny, so they stay on CPU.
        self._head_rows = core.compile_model(head_rows, "CPU") if head_rows is not None else None

        self._te = core.compile_model(emb, self.device)
        self._lm = core.compile_model(lm, self.device)
        self._hidden_port = self._lm.output(HIDDEN_NAME)
        self._logits_port = self._lm.output(LOGITS_NAME) if self.token_form else None
        logger.info(
            "Compiled backbone %s on %s (hidden=%d, position_ids rank=%d, stateful=%s, "
            "surgery=%s, head rows from %s, masked linear-attention layers=%d, "
            "token patch=%s)",
            self.ir_dir,
            self.device,
            self.hidden_size,
            self.pos_rank,
            self.stateful,
            self.surgery,
            self.head_source,
            self.masked_linear_attention_layers,
            self.token_patch_digest or "none",
        )

    def encode(self, text: str) -> np.ndarray:
        """Tokenize ``text`` to a 1-D int64 id array."""
        return self.tokenizer.encode(text)

    def embed(self, ids: np.ndarray) -> np.ndarray:
        """Token embeddings ``[1, L, H]`` (float32) for a 1-D id array."""
        ids_2d = np.asarray(ids, dtype=np.int64).reshape(1, -1)
        out = self._te.create_infer_request().infer([ids_2d])
        return out[self._te.output(0)].astype(np.float32)

    def _infer_lm(self, embeds: np.ndarray, attention_mask: Optional[np.ndarray]):
        """One language-model pass over ``embeds [1, L, H]``; returns all outputs."""
        seq_len = embeds.shape[1]
        positions = np.arange(seq_len, dtype=np.int64)[None]
        if self.pos_rank == 3:  # mRoPE: 4 sections, all = arange for pure text
            positions = np.tile(positions[None], (4, 1, 1))
        if attention_mask is None:
            mask = np.ones((1, seq_len), dtype=np.int64)
        else:
            mask = np.asarray(attention_mask, dtype=np.int64).reshape(1, seq_len)
        feed = {
            "inputs_embeds": embeds,
            "attention_mask": mask,
            "position_ids": positions,
        }
        if self._has_beam:
            feed["beam_idx"] = np.zeros((1,), dtype=np.int32)

        req = self._lm.create_infer_request()
        if self.stateful:
            req.reset_state()  # fresh state for this independent sequence
        return req.infer(feed)

    def last_hidden(
        self, embeds: np.ndarray, attention_mask: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """Post-norm hidden state ``[H]`` at the last position of ``embeds [1, L, H]``.

        ``attention_mask`` (``[L]`` or ``[1, L]``, default all ones) masks
        positions out of attention, e.g. the pad block between a soft prompt and
        the query. Positions are numbered ``0..L-1`` straight through, masked
        ones included -- what HuggingFace does when no ``position_ids`` are
        given, i.e. how the soft prompts were trained. The last position must be
        a real token.
        """
        out = self._infer_lm(embeds, attention_mask)
        return np.asarray(out[self._hidden_port][0, -1], dtype=np.float32)

    def last_logits(
        self, embeds: np.ndarray, attention_mask: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """Full-vocabulary logits ``[V]`` at the last position of ``embeds [1, L, H]``.

        Only token-form runtimes keep the lm_head. Mask semantics as
        :meth:`last_hidden`; the last position must be a real token.
        """
        if self._logits_port is None:
            raise ValueError(f"{self.ir_dir}: no logits output on this runtime (not token-form)")
        out = self._infer_lm(embeds, attention_mask)
        return np.asarray(out[self._logits_port][0], dtype=np.float32)

    def class_logits(
        self, embeds: np.ndarray, attention_mask: Optional[np.ndarray] = None
    ) -> np.ndarray:
        """The class tokens' logits ``[C]`` -- :meth:`last_logits` read at the patch's class ids.

        Ordered by the patch's class ids, i.e. class order.
        """
        return self.last_logits(embeds, attention_mask)[self._class_ids]

    def strip_prompt_prefix(self, ids: np.ndarray) -> np.ndarray:
        """Remove the prefix the tokenizer adds to every encoding (Llama's BOS).

        Single-token answer codes encode as ``[BOS, token]`` on such backbones;
        the prefix is not part of the code. Backbones without a prefix (Qwen)
        return the ids unchanged.
        """
        if len(ids) and np.array_equal(ids[: len(self._bos_prefix)], self._bos_prefix):
            return ids[len(self._bos_prefix):]
        return ids

    def label_rows(self, ids: Sequence[int]) -> np.ndarray:
        """lm_head rows ``[len(ids), H]`` (float32) for ``ids``: the hard classifier's head.

        ``last_hidden(...) @ label_rows(ids).T`` equals those tokens' entries in
        the full vocab logits. Read from the lm_head weight when the IR has one;
        otherwise the token embeddings, which is exact only for tied, uncompressed
        weights.
        """
        ids = np.asarray(ids, dtype=np.int64).reshape(-1)
        if self._head_rows is not None:
            out = self._head_rows.create_infer_request().infer([ids])
            return out[self._head_rows.output(0)].astype(np.float32)
        if not self.tied:
            raise ValueError(
                f"{self.ir_dir}: lm_head is not tied to the embeddings and the IR has no "
                f"{LM_HEAD_XML}; cannot build the head rows"
            )
        return self.embed(ids)[0]


# Weak values: a runtime lives as long as some classifier holds it, so a backbone
# no engine uses any more is released rather than kept compiled forever. Token
# patches key separately: a patched runtime is only shared by the versions that
# wrote exactly those rows.
_RUNTIMES: "WeakValueDictionary[Tuple[str, str, Optional[str]], BackboneRuntime]" = (
    WeakValueDictionary()
)
_RUNTIMES_LOCK = threading.Lock()


def _reusable_runtime(path: str, device: str) -> Optional[BackboneRuntime]:
    """Any live runtime of ``(path, device)`` for unpatched work, a patched one first.

    Preferring a patched runtime lets callers that re-resolve (see
    :class:`~.classifier.OVQwenClassifier`) move onto it, so an unpatched
    runtime compiled earlier is released instead of kept next to it.
    Caller holds ``_RUNTIMES_LOCK``.
    """
    unpatched = None
    for (cand_path, cand_device, digest), candidate in list(_RUNTIMES.items()):
        if cand_path == path and cand_device == device:
            if digest is not None:
                return candidate
            unpatched = candidate
    return unpatched


def get_runtime(
    ir_dir: str, device: str = "CPU", token_patch: Optional[VocabTokenPatch] = None
) -> BackboneRuntime:
    """The runtime for ``(ir_dir, device, token_patch)``, compiled on first use.

    A token-form version compiles its own model, keyed by the patch digest
    (see the module docstring). Unpatched callers (hard versions, multi-class
    rules) reuse *any* runtime already compiled for the backbone, a patched
    one first -- a patch only touches free rows, so a patched runtime serves
    them unchanged; that keeps e.g. a multi-class rule from compiling a second
    2B next to the patched default version.
    """
    path = str(Path(ir_dir).expanduser().resolve())
    key = (path, device, token_patch.digest if token_patch is not None else None)
    with _RUNTIMES_LOCK:
        if token_patch is None:
            reusable = _reusable_runtime(path, device)
            if reusable is not None:
                return reusable
        runtime = _RUNTIMES.get(key)
        if runtime is None:
            runtime = _RUNTIMES[key] = BackboneRuntime(key[0], device, token_patch=token_patch)
        return runtime


def get_tokenizer(ir_dir: str) -> Tokenizer:
    """The tokenizer of ``ir_dir``: a compiled runtime's if there is one, else a new one."""
    root = str(Path(ir_dir).expanduser().resolve())
    with _RUNTIMES_LOCK:
        for (path, _device, _digest), runtime in list(_RUNTIMES.items()):
            if path == root:
                return runtime.tokenizer
    return Tokenizer(root)
