# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Qwen text embedding handler with OpenVINO acceleration."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Union, Any

import torch
import torch.nn.functional as F
from torch import Tensor
from transformers import AutoModel, AutoTokenizer

from ..base import BaseEmbeddingModel
from ...utils import logger

try:  # pragma: no cover - optional dependency at runtime
    from optimum.intel import OVModelForFeatureExtraction  # type: ignore
except Exception:  # pragma: no cover - handled at runtime
    OVModelForFeatureExtraction = None  # type: ignore


def _env_int(name: str, default: int) -> int:
    """Read a positive integer environment variable with a safe fallback."""
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        parsed = int(raw)
    except ValueError:
        logger.warning("Ignoring non-integer value for %s: %s", name, raw)
        return default
    if parsed <= 0:
        logger.warning("Ignoring non-positive value for %s: %s", name, raw)
        return default
    return parsed


def _env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment variable with a safe fallback."""
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    normalized = raw.strip().lower()
    if normalized in ("1", "true", "yes", "on"):
        return True
    if normalized in ("0", "false", "no", "off"):
        return False
    logger.warning("Ignoring non-boolean value for %s: %s", name, raw)
    return default





class QwenEmbeddingHandler(BaseEmbeddingModel):
    """Handler for Qwen text embedding models."""

    DEFAULT_TASK_DESCRIPTION = (
        "Given a web search query, retrieve relevant passages that answer the query"
    )
    INSTRUCTION_TEMPLATE = "Instruct: {task_description}\nQuery:{query}"

    # Devices whose OpenVINO plugin cannot compile fully dynamic shapes.
    STATIC_SHAPE_DEVICE_PREFIXES = ("NPU",)
    # QwenText exists to embed long-form text, so the static NPU shape must stay
    # well clear of the CLIP-family limits it is meant to beat (CLIP 77 tokens,
    # SigLIP 64, CN-CLIP 52). Measured on the Intel NPU of an Intel(R) Core(TM)
    # Ultra 9 285H with Qwen3-Embedding-0.6B
    # (batch 1, compile time is one-time and cached per shape):
    #   512 -> 11s compile, 0.26s/infer     2048 -> 75s compile, 1.7s/infer
    #   1024 -> 22s compile, 0.63s/infer    4096 -> 413s compile, 4.6s/infer
    #   8192 -> 1193s compile, 35.8s/infer  (impractical for serving)
    # 2048 is the best trade-off: ~27x the CLIP context, covers a typical
    # 1000-word video summary in full, and keeps latency usable.
    DEFAULT_STATIC_SEQ_LEN = 2048
    # Selectable static sequence lengths. Restricted to powers of two because
    # each distinct value costs its own (cached) NPU compilation, so an
    # open-ended value would silently multiply compile artifacts and startup
    # time. Values below 128 are excluded: they would drop QwenText to around
    # the CLIP-family context (CLIP 77, SigLIP 64, CN-CLIP 52) and remove the
    # only reason to choose this model family.
    ALLOWED_STATIC_SEQ_LENS = (128, 256, 512, 1024, 2048, 4096, 8192)

    # Batch 1 is the only shape that compiles for Qwen3-Embedding on NPU, so it
    # is a constant rather than a setting: there is no other working value to
    # choose. The rejection is raised by the NPU compiler itself and the message
    # varies by OpenVINO release (a ConstantFolding buffer-size mismatch on
    # 2026.2.x, a Level Zero / VCL "Compilation failed" on 2026.4.0). Every
    # NPU_BATCH_MODE was tried: COMPILER and AUTO both fail in the compiler,
    # PLUGIN fails immediately with "Cannot debatch a model". Larger request
    # batches are split into batch-1 passes at inference time instead.
    STATIC_BATCH_SIZE = 1

    # Fraction of each chunk repeated at the start of the next one. A sentence
    # straddling a chunk boundary would otherwise be split across two vectors
    # and be well represented in neither. Not configurable: sweeping 0.0-0.45
    # on NPU moved the final embedding by only 1-2% (cosine 0.974-0.989 against
    # this default) while raising the chunk count - and so the inference cost -
    # by up to 50%, so there is no setting a user could pick that is reliably
    # better, only slower.
    CHUNK_OVERLAP_RATIO = 0.1

    def __init__(self, model_config: Dict[str, Any]):
        config = dict(model_config)
        config.setdefault("modalities", ["text"])
        super().__init__(config)
        self.model_config = config

        self.hf_model_id: str = config["hf_model_id"]
        self.max_length: int = config.get("max_length", 8192)
        self.task_description: str = config.get(
            "task_description", self.DEFAULT_TASK_DESCRIPTION
        )
        self.instruction_template: str = config.get(
            "instruction_template", self.INSTRUCTION_TEMPLATE
        )
        self.weight_format: str = config.get("weight_format", "int8").lower()
        self.revision: str | None = config.get("revision")
        self.trust_remote_code: bool = bool(config.get("trust_remote_code", True))
        self.use_openvino: bool = bool(config.get("use_openvino", False))
        self.device: str = config.get("device", "CPU")

        # The NPU compiler rejects graphs with more than one unbounded dynamic
        # dimension, so the exported (dynamic batch, dynamic sequence) IR must
        # be reshaped there. CPU and GPU handle the dynamic IR natively and
        # gain nothing from a fixed shape, so this follows the device with no
        # override: forcing it off on NPU only reproduces the original
        # "expected exactly 1 dynamic output bound dimension, got 2" failure.
        self.needs_static_shapes: bool = self.device.upper().startswith(
            self.STATIC_SHAPE_DEVICE_PREFIXES
        )
        self.static_seq_len: int = self._resolve_static_seq_len()

        # Text longer than the token budget is split, embedded chunk by chunk,
        # and averaged back into one vector. Without this the tokenizer drops
        # the tail entirely, so two documents sharing a long prefix produce
        # near-identical embeddings regardless of how they differ later.
        self.chunk_long_text: bool = _env_flag("EMBEDDING_CHUNK_LONG_TEXT", True)

        self.model = None
        self.tokenizer = None
        self._embedding_dim: int | None = None

    def _resolve_static_seq_len(self) -> int:
        """
        Resolve the static sequence length from ``EMBEDDING_STATIC_SEQ_LEN``.

        The value is snapped to the nearest allowed length that is *not
        smaller* than the request. Rounding up rather than down is deliberate:
        rounding down would truncate more input than the operator asked for and
        silently discard content, whereas rounding up only costs latency.
        Values above the model's ``max_length`` (or the largest supported
        length) are clamped down, since the model cannot attend further.
        """
        candidates = [n for n in self.ALLOWED_STATIC_SEQ_LENS if n <= self.max_length]
        if not candidates:
            return min(self.max_length, self.DEFAULT_STATIC_SEQ_LEN)

        default = (
            self.DEFAULT_STATIC_SEQ_LEN
            if self.DEFAULT_STATIC_SEQ_LEN in candidates
            else candidates[-1]
        )
        requested = _env_int("EMBEDDING_STATIC_SEQ_LEN", default)
        if requested == default:
            return default

        resolved = next((n for n in candidates if n >= requested), candidates[-1])
        if resolved != requested:
            logger.warning(
                "EMBEDDING_STATIC_SEQ_LEN=%d is not a supported static sequence "
                "length; using %d instead. Supported values (capped at the "
                "model's max_length %d): %s.",
                requested,
                resolved,
                self.max_length,
                ", ".join(str(n) for n in candidates),
            )
        return resolved

        # ------------------------------------------------------------------
    # Base overrides
    # ------------------------------------------------------------------
    def load_model(self) -> None:
        """Load tokenizer and either Torch or OpenVINO model."""
        logger.info(
            "Loading Qwen embedding model %s using %s",
            self.hf_model_id,
            "OpenVINO" if self.use_openvino else "PyTorch",
        )
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.hf_model_id,
            trust_remote_code=self.trust_remote_code,
            padding_side="left",
            revision=self.revision,
        )

        if self.use_openvino:
            if OVModelForFeatureExtraction is None:
                raise RuntimeError(
                    "optimum-intel is required for OpenVINO execution but could not be imported"
                )
            self.model = self._load_openvino_model()
        else:
            self.model = AutoModel.from_pretrained(
                self.hf_model_id,
                trust_remote_code=self.trust_remote_code,
                revision=self.revision,
            )
            self.model.eval()
            # Keep model on CPU for PyTorch inference (text embeddings work well on CPU)
        logger.info("Qwen model loaded successfully")

    @property
    def _static_shapes_active(self) -> bool:
        """True when inference runs against a model compiled to a fixed shape."""
        return self.use_openvino and self.needs_static_shapes

    def encode_text(self, texts: Union[str, List[str]]) -> torch.Tensor:
        if isinstance(texts, str):
            texts = [texts]
        prepared_texts = self.prepare_documents(list(texts))

        budget = self.get_max_text_tokens()
        # Chunking only exists to work around the fixed sequence length that a
        # static-shape device forces. CPU and GPU run the model dynamically at
        # its full context, so they keep their original truncation behaviour
        # and are unaffected by the chunking settings.
        if not self._static_shapes_active or not self.chunk_long_text or not budget:
            return self._embed_texts(prepared_texts, warn_on_truncation=True)

        # Map every input to its chunks, then embed all chunks in one pass so
        # the batching/padding logic below stays unchanged.
        chunks_per_text = [self._chunk_to_fit(t, budget) for t in prepared_texts]
        if all(len(c) == 1 for c in chunks_per_text):
            return self._embed_texts(prepared_texts, warn_on_truncation=True)

        total_chunks = sum(len(c) for c in chunks_per_text)
        logger.info(
            "%d of %d input(s) exceeded the %d-token budget; embedding them as "
            "%d chunks and combining each into a single vector.",
            sum(1 for c in chunks_per_text if len(c) > 1),
            len(prepared_texts),
            budget,
            total_chunks,
        )

        flat = [chunk for chunks in chunks_per_text for chunk, _ in chunks]
        chunk_embeddings = self._embed_texts(flat, warn_on_truncation=False)

        combined = []
        offset = 0
        for chunks in chunks_per_text:
            span = chunk_embeddings[offset : offset + len(chunks)]
            offset += len(chunks)
            if len(chunks) == 1:
                combined.append(span[0])
                continue
            # Weight each chunk by the number of tokens it contributes that no
            # earlier chunk already covered. Windows are equal-sized, so an
            # unweighted mean (or one weighted by total tokens) would let a
            # trailing window that is almost entirely overlap count as much as
            # a full one: a document one token past the budget would swing its
            # embedding by ~50%. Counting each token once keeps the result a
            # property of the document rather than of where the window grid
            # happened to land.
            weights = torch.tensor(
                [novel for _, novel in chunks],
                dtype=span.dtype,
                device=span.device,
            )
            if float(weights.sum()) <= 0:  # defensive: never divide by zero
                weights = torch.ones_like(weights)
            weights = weights / weights.sum()
            combined.append((span * weights.unsqueeze(1)).sum(dim=0))

        embeddings = F.normalize(torch.stack(combined), p=2, dim=1)
        return embeddings.to(torch.float32).cpu()

    def _chunk_to_fit(self, text: str, budget: int) -> List[Tuple[str, int]]:
        """
        Split *text* into overlapping pieces that each fit within *budget* tokens.

        Returns ``(chunk_text, novel_token_count)`` pairs, where the count is
        the number of tokens the chunk adds that no earlier chunk covered; it
        is the weight used to combine the chunk vectors.

        Windows are cut over the model's own token ids rather than characters,
        so a chunk can never overflow the budget. Each window is decoded back to
        text and re-tokenized by the normal path, which re-appends the special
        token that last-token pooling depends on; slicing ids directly would
        leave interior chunks ending on an arbitrary content token.
        """
        ids = self.tokenizer(text, truncation=False)["input_ids"]
        # Drop the trailing special token; re-tokenizing each chunk re-adds it.
        if ids and ids[-1] in self.tokenizer.all_special_ids:
            ids = ids[:-1]
        if len(ids) + 1 <= budget:
            return [(text, max(1, len(ids)))]

        window = max(1, budget - 1)  # leave room for the re-added special token
        overlap = min(int(window * self.CHUNK_OVERLAP_RATIO), window - 1)
        stride = max(1, window - overlap)

        chunks: List[Tuple[str, int]] = []
        covered = 0
        start = 0
        while start < len(ids):
            end = min(start + window, len(ids))
            # Anchor a short trailing window to the end of the text instead of
            # emitting a stub. A full-width final chunk carries enough context
            # to embed meaningfully; the extra overlap it picks up is already
            # discounted by the novel-token weighting.
            if end == len(ids) and end - start < window:
                start = max(0, len(ids) - window)
            piece = ids[start:end]
            if not piece:
                break
            novel = max(0, end - max(start, covered))
            covered = max(covered, end)
            decoded = self.tokenizer.decode(piece, skip_special_tokens=True).strip()
            # A chunk adding no new tokens would cost a full inference pass and
            # contribute nothing, so drop it.
            if decoded and novel > 0:
                chunks.append((decoded, novel))
            if end >= len(ids):
                break
            start += stride
        return chunks or [(text, 1)]

    def _embed_texts(
        self, prepared_texts: List[str], warn_on_truncation: bool = True
    ) -> torch.Tensor:
        """Tokenize, run the model, and pool into normalized embeddings."""
        use_static = self._static_shapes_active
        tokenized = self.tokenizer(
            prepared_texts,
            padding="max_length" if use_static else True,
            truncation=True,
            max_length=self.static_seq_len if use_static else self.max_length,
            return_tensors="pt",
        )
        if use_static and warn_on_truncation:
            self._warn_if_truncated(prepared_texts)
        # Tokenized tensors stay on CPU (model is on CPU or handled by OpenVINO)

        if use_static:
            last_hidden_state = self._infer_static_batches(tokenized)
        elif self.use_openvino:
            last_hidden_state = self.model(**tokenized).last_hidden_state
        else:
            with torch.no_grad():
                last_hidden_state = self.model(**tokenized).last_hidden_state

        embeddings = self._last_token_pool(
            last_hidden_state, tokenized["attention_mask"]
        )
        embeddings = F.normalize(embeddings, p=2, dim=1)
        embeddings = embeddings.to(torch.float32).cpu()
        if self._embedding_dim is None:
            self._embedding_dim = embeddings.shape[-1]
        return embeddings

    def _warn_if_truncated(self, prepared_texts: List[str]) -> None:
        """
        Log when an input exceeds the compiled static sequence length.

        Truncation silently discards the tail of a document, which produces a
        vector that ignores the dropped content, so it must be visible in logs
        rather than failing quietly. Only the token count is logged, never the
        text itself.
        """
        over = [
            n
            for n in (
                len(self.tokenizer(t, truncation=False)["input_ids"])
                for t in prepared_texts
            )
            if n > self.static_seq_len
        ]
        if not over:
            return
        logger.warning(
            "%d of %d input(s) exceeded the static sequence length %d on %s and "
            "were truncated (largest: %d tokens); the discarded tail does not "
            "affect the embedding. Raise EMBEDDING_STATIC_SEQ_LEN or split the "
            "text into smaller passages.",
            len(over),
            len(prepared_texts),
            self.static_seq_len,
            self.device,
            max(over),
        )

    def _infer_static_batches(self, tokenized) -> torch.Tensor:
        """
        Run inference against a model compiled for a fixed batch size.

        Oversized batches are split into chunks of ``STATIC_BATCH_SIZE`` and an
        undersized final chunk is padded by repeating its last row (repeating a
        real row instead of zero-padding avoids all-masked rows, which would
        make the attention softmax produce NaNs). Padding rows are dropped from
        the output before the chunks are concatenated.
        """
        input_ids = tokenized["input_ids"]
        attention_mask = tokenized["attention_mask"]
        total = int(input_ids.shape[0])
        batch = self.STATIC_BATCH_SIZE

        outputs = []
        for start in range(0, total, batch):
            end = min(start + batch, total)
            chunk_ids = input_ids[start:end]
            chunk_mask = attention_mask[start:end]
            valid = end - start

            if valid < batch:
                pad = batch - valid
                chunk_ids = torch.cat([chunk_ids, chunk_ids[-1:].repeat(pad, 1)])
                chunk_mask = torch.cat([chunk_mask, chunk_mask[-1:].repeat(pad, 1)])

            chunk_output = self.model(
                input_ids=chunk_ids, attention_mask=chunk_mask
            ).last_hidden_state
            outputs.append(chunk_output[:valid])

        return torch.cat(outputs, dim=0)

    def encode_image(self, images):  # pragma: no cover - should be guarded upstream
        raise NotImplementedError("Qwen text embedding handler does not support images")

    def get_max_text_tokens(self) -> int:
        """
        Return the effective text token budget for the current configuration.

        On accelerators that require a static shape (NPU) the compiled
        sequence length is the real ceiling, not the model's ``max_length``,
        so report that instead. Anything beyond it is truncated.
        """
        if self._static_shapes_active:
            return self.static_seq_len
        return self.max_length

    def convert_to_openvino(self, ov_models_dir: str) -> tuple:
        xml_path = self._export_openvino(Path(ov_models_dir))
        return (str(xml_path),)

    def get_embedding_dim(self) -> int:
        if self._embedding_dim is not None:
            return self._embedding_dim
        probe = self.prepare_documents(["embedding-dimension-probe"])
        embedding = self.encode_text(probe)
        self._embedding_dim = int(embedding.shape[-1])
        return self._embedding_dim

    def prepare_query(self, text: str) -> str:
        return self.instruction_template.format(
            task_description=self.task_description,
            query=text,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _load_openvino_model(self):
        xml_path = self._export_openvino(Path(self.ov_models_dir))
        logger.info("Loading OpenVINO model from %s on %s", xml_path, self.device)

        common_kwargs = {
            "device": self.device,
            "export": False,
            "trust_remote_code": self.trust_remote_code,
        }

        if not self.needs_static_shapes:
            return OVModelForFeatureExtraction.from_pretrained(
                xml_path.parent, **common_kwargs
            )

        # The exported IR is fully dynamic on both batch and sequence length.
        # The NPU compiler needs exactly one (at most) unbounded dimension, so
        # load without compiling, pin both dimensions, then compile.
        ov_config = {}
        cache_dir = self._resolve_cache_dir(xml_path.parent)
        if cache_dir:
            ov_config["CACHE_DIR"] = cache_dir

        logger.info(
            "Device %s requires static shapes: reshaping Qwen model to "
            "[%d, %d] (batch, sequence_length) before compilation.",
            self.device,
            self.STATIC_BATCH_SIZE,
            self.static_seq_len,
        )
        if self.static_seq_len < self.max_length:
            if self.chunk_long_text:
                logger.info(
                    "Static sequence length %d is shorter than the model max_length "
                    "%d; longer inputs are split into chunks and combined into a "
                    "single embedding. Raise EMBEDDING_STATIC_SEQ_LEN to process "
                    "more text per pass, or set EMBEDDING_CHUNK_LONG_TEXT=false to "
                    "truncate instead.",
                    self.static_seq_len,
                    self.max_length,
                )
            else:
                logger.warning(
                    "Static sequence length %d is shorter than the model max_length "
                    "%d and chunking is disabled; longer inputs will be truncated "
                    "on %s. Override with EMBEDDING_STATIC_SEQ_LEN.",
                    self.static_seq_len,
                    self.max_length,
                    self.device,
                )

        model = OVModelForFeatureExtraction.from_pretrained(
            xml_path.parent,
            compile=False,
            ov_config=ov_config or None,
            **common_kwargs,
        )
        model.reshape(self.STATIC_BATCH_SIZE, self.static_seq_len)
        model.compile()
        return model

    def _resolve_cache_dir(self, export_dir: Path) -> str | None:
        """
        Resolve a per-shape OpenVINO compiled-blob cache directory.

        Compiled blobs are only valid for the exact device and static shape
        they were produced for, so the shape is part of the path. Returns
        ``None`` when caching is disabled or the directory is not writable.
        """
        if (os.getenv("OV_ENABLE_MODEL_CACHE") or "").strip().lower() in {
            "0",
            "false",
            "no",
            "off",
        }:
            logger.info("OpenVINO model caching disabled via OV_ENABLE_MODEL_CACHE.")
            return None

        base = os.getenv("OV_CACHE_DIR") or os.getenv("EMBEDDING_OV_CACHE_DIR")
        base_path = Path(base) if base else export_dir / "ov_cache"
        shape_key = (
            f"{re.sub(r'[^a-zA-Z0-9]+', '_', self.device).lower()}"
            f"_{self.STATIC_BATCH_SIZE}x{self.static_seq_len}"
        )
        cache_dir = base_path / shape_key
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                "Could not create OpenVINO cache directory %s: %s. "
                "Continuing without cache (compilation runs on every startup).",
                cache_dir,
                exc,
            )
            return None
        logger.info("OpenVINO model caching enabled. CACHE_DIR=%s", cache_dir)
        return str(cache_dir)

    def _export_openvino(self, base_dir: Path) -> Path:
        export_dir = base_dir / self._sanitized_model_dir() / self.weight_format.upper()
        export_dir.mkdir(parents=True, exist_ok=True)
        xml_path = export_dir / "openvino_model.xml"
        if xml_path.exists():
            logger.info("Reusing existing OpenVINO artifacts at %s", export_dir)
            return xml_path

        if OVModelForFeatureExtraction is None:
            raise RuntimeError(
                "optimum-intel is required for OpenVINO export but could not be imported"
            )

        logger.info(
            "Exporting Qwen model %s to OpenVINO (%s) at %s",
            self.hf_model_id,
            self.weight_format.upper(),
            export_dir,
        )
        self._export_via_python_api(export_dir)
        return xml_path

    def _export_via_python_api(self, export_dir: Path) -> None:
        """
        Export model to OpenVINO format using optimum-intel Python API.
        
        This is equivalent to:
        optimum-cli export openvino --model <model> --task feature-extraction 
                                    --weight-format <format> --trust-remote-code
        """
        try:
            logger.info("Exporting model using optimum-intel Python API...")
            
            # Determine weight quantization parameter
            # int8/int4 -> load_in_8bit=True/load_in_4bit=True (applied during export)
            export_kwargs = {
                "export": True,  # Trigger conversion from PyTorch to OpenVINO
                "trust_remote_code": self.trust_remote_code,
            }
            
            if self.revision:
                export_kwargs["revision"] = self.revision
            
            # Apply weight compression based on format
            if self.weight_format == "int8":
                export_kwargs["load_in_8bit"] = True
            elif self.weight_format == "int4":
                export_kwargs["load_in_4bit"] = True
            # fp16/fp32 don't need special flags (default behavior)
            
            # Export using OVModelForFeatureExtraction
            logger.debug(f"Export kwargs: {export_kwargs}")
            ov_model = OVModelForFeatureExtraction.from_pretrained(
                self.hf_model_id,
                **export_kwargs
            )
            
            # Save the exported model
            logger.info(f"Saving exported model to {export_dir}")
            ov_model.save_pretrained(export_dir)
            logger.info("Export completed successfully")
            # Clean up
            del ov_model
            logger.debug("Cleaned up export model from memory")
            
        except Exception as exc:
            raise RuntimeError(
                f"Failed to export model {self.hf_model_id} to OpenVINO format: {exc}"
            ) from exc

    @staticmethod
    def _last_token_pool(last_hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
        left_padding = attention_mask[:, -1].sum() == attention_mask.shape[0]
        if left_padding:
            return last_hidden_states[:, -1]
        sequence_lengths = attention_mask.sum(dim=1) - 1
        batch_size = last_hidden_states.shape[0]
        return last_hidden_states[
            torch.arange(batch_size, device=last_hidden_states.device),
            sequence_lengths,
        ]

    def _sanitized_model_dir(self) -> str:
        sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", self.hf_model_id)
        return sanitized.lower().strip("_")