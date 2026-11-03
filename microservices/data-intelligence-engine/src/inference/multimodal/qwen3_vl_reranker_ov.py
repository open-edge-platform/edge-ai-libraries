# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Standalone OpenVINO scorer for the official Qwen3-VL reranker."""

import json
import logging
import math
from pathlib import Path

import numpy as np


logger = logging.getLogger(__name__)


class OpenVINOVLReranking:
    """Scores query/document pairs with mode-specific OpenVINO graphs."""

    def __init__(self, model_id_or_path: str, device: str = "CPU"):
        import openvino as ov
        from transformers import AutoProcessor

        directory = Path(model_id_or_path)
        score_config = directory / "1_LogitScore" / "config.json"
        if not score_config.is_file():
            raise FileNotFoundError(
                f"{directory} needs official 1_LogitScore/config.json"
            )
        ids = json.loads(score_config.read_text())
        self.config = json.loads((directory / "config.json").read_text())
        manifest = directory / "export_shapes.json"
        self.export_shapes = json.loads(manifest.read_text()) if manifest.is_file() else None
        self.true_id = int(ids["true_token_id"])
        self.false_id = int(ids["false_token_id"])
        self.processor = AutoProcessor.from_pretrained(
            str(directory), trust_remote_code=True, padding_side="left",
            local_files_only=True,
        )
        self.processor.tokenizer.padding_side = "left"
        self.directory = directory
        self.device = device
        self.core = ov.Core()
        # Compiled-model cache: first-time graph compilation (tens of seconds on
        # Intel GPU) is paid once per shape ever, not once per process start.
        cache = directory / ".ov_cache"
        try:
            cache.mkdir(exist_ok=True)
            self.core.set_property({"CACHE_DIR": str(cache)})
        except OSError:
            logger.warning("model compile cache %s is not writable", cache)
        self.requests = {}

    def _request(self, mode, values):
        # The Intel GPU compiler needs concrete video shapes for this traced
        # full-forward graph. Query/document pairs sharing shapes reuse it.
        key = (mode, tuple((name, tuple(np.asarray(value).shape)) for name, value in values.items())) if mode == "video" else mode
        cached = self.requests.get(key)
        if cached is not None:
            return cached
        ir = self.directory / f"reranker_{mode}.xml"
        if not ir.is_file():
            raise FileNotFoundError(f"{ir} is not exported")
        if mode == "video":
            graph = self.core.read_model(ir)
            shapes = {
                port.get_any_name(): list(np.asarray(values[port.get_any_name()]).shape)
                for port in graph.inputs
            }
            graph.reshape(shapes)
            compiled = self.core.compile_model(graph, self.device)
        else:
            compiled = self.core.compile_model(ir, self.device)
        output = next(
            (port for port in compiled.outputs if "logits" in port.get_names()), None
        )
        if output is None:
            raise ValueError(f"{ir} must expose a logits output")
        cached = (compiled.create_infer_request(), tuple(compiled.inputs), output)
        self.requests[key] = cached
        return cached

    def _prepare(self, query, document):
        """The CPU half of scoring one pair: encode, positions, shape checks."""
        from inference.multimodal.qwen3_vl_reranker_inputs import encode, pad_pair, rope_position_ids

        mode = "video" if "video" in document else "image" if "image" in document else "text"
        values = encode(self.processor, query, document)
        if mode != "text":
            values["position_ids"] = rope_position_ids(values, self.config)
            if self.export_shapes is None:
                raise ValueError("visual reranker package lacks export_shapes.json")
            for name, expected in self.export_shapes["modes"][mode].items():
                if np.asarray(values[name]).tolist() != expected:
                    raise ValueError(
                        f"{mode} input grid differs from the exported IR; "
                        "re-export that mode with matching visual inputs"
                    )
        if mode == "video":
            # One canonical shape per video pair: pad the token axis to the
            # export bucket so every video query shares a single compiled graph
            # instead of recompiling per query length. Oversized pairs fall
            # back to the per-shape compile.
            bucket = (self.export_shapes or {}).get("video_seq_bucket")
            length = len(values["input_ids"][0])
            if bucket is not None and length <= bucket:
                values, values["position_ids"] = pad_pair(
                    values, values["position_ids"], bucket,
                    self.processor.tokenizer.pad_token_id,
                )
        return mode, values

    @staticmethod
    def _feeds(inputs, values):
        feeds = {}
        missing = []
        for port in inputs:
            name = next((name for name in port.get_names() if name in values), None)
            if name is None:
                missing.append(port.get_any_name())
            else:
                feeds[port.get_any_name()] = np.asarray(values[name])
        if missing:
            raise ValueError(f"reranker IR requires unavailable processor inputs: {sorted(missing)}")
        return feeds

    def _logit_score(self, logits):
        """Sigmoid over the yes/no logit gap at the final token."""
        logits = np.asarray(logits)
        if logits.ndim == 3:
            logits = logits[0, -1]
        elif logits.ndim == 2:
            logits = logits[0]
        if logits.ndim != 1 or logits.size <= max(self.true_id, self.false_id):
            raise ValueError("reranker IR logits have the wrong shape")
        delta = float(logits[self.true_id] - logits[self.false_id])
        score = float(1.0 / (1.0 + np.exp(-np.clip(delta, -80, 80))))
        if not math.isfinite(score):
            raise ValueError("nonfinite media rerank score")
        return score

    def score(self, query, document):
        return self.score_batch(query, [document])[0]

    def score_batch(self, query, documents):
        """Score every pair and return the scores in submission order.

        Each pair runs its own batch-1 inference: the traced causal mask covers
        a single pair, so pairs cannot share one batched call. A failed pair
        fails the batch: the caller degrades the whole request rather than mix
        rerank and ANN scores in one ranking.
        """
        scores = []
        for document in documents:
            mode, values = self._prepare(query, document)
            request, inputs, output = self._request(mode, values)
            logits = request.infer(self._feeds(inputs, values))[output]
            scores.append(self._logit_score(logits))
        return scores
