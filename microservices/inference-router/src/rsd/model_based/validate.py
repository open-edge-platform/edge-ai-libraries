# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Backbone compatibility checks for a classifier version.

Three levels run before a version is trusted on a backbone:

- **L1 model name**: the version's ``model_name`` must be a known backbone
  (and match the requested backbone key when one is given).
- **L2 tokenizer**: the runtime's tokenizer must reproduce the packed probe
  token ids; for hard versions each answer code (``label_tokens``, e.g. E/H or
  A/B/C -- not the class names) must still be exactly one token, the packed id.
  Token-form soft versions additionally have their vocabulary ids checked
  against the backbone's free-row layout (:func:`.vocab_tokens.check_token_ids`).
- **L3 hidden fingerprint**: every probe's post-norm hidden (pure backbone --
  no template, no soft prefix) must match the packed fingerprint by cosine;
  hard versions additionally match the packed head rows against the
  backbone's rows for the label tokens. Token-form versions then verify the
  rows actually written into the graph read back as the packed data (within
  the constant's rounding -- :func:`check_vocab_rows`).

Runs wherever a version meets a backbone: the registry's version-loading
path, before a version serves any request.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import numpy as np

from src.rsd.model_based.settings import KNOWN_BACKBONES, fingerprint_min_cos
from src.rsd.model_based.vocab_tokens import check_token_ids


class VersionValidationError(Exception):
    """A compatibility level failed; ``level`` is ``"L1"`` / ``"L2"`` / ``"L3"``."""

    def __init__(self, level: str, message: str) -> None:
        super().__init__(f"{level}: {message}")
        self.level = level
        self.message = message


def _cosine(a, b) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    norm = float(np.linalg.norm(a) * np.linalg.norm(b))
    return 0.0 if norm == 0.0 else float(a @ b / norm)


def fingerprint_rows(runtime, probes) -> np.ndarray:
    """Post-norm last-position hidden per probe -- pure backbone, no template."""
    rows = [
        np.asarray(runtime.last_hidden(runtime.embed(runtime.encode(probe))), dtype=np.float64)
        for probe in probes
    ]
    return np.stack(rows)


def check_model_name(bundle, backbone: Optional[str] = None) -> Dict[str, Any]:
    """L1 alone: needs only the bundle's metadata, no backbone.

    Returns ``{"backbone", "model_name", "L1": "ok"}``; raises
    :class:`VersionValidationError` when the version's ``model_name`` is not
    ``backbone``'s (or, without ``backbone``, not any known backbone).
    """
    model_name = bundle.model_name
    if backbone is not None:
        official = KNOWN_BACKBONES.get(backbone)
        if official != model_name:
            raise VersionValidationError(
                "L1",
                f"version model_name {model_name!r} does not match backbone "
                f"{backbone!r} ({official!r})",
            )
        return {"backbone": backbone, "model_name": model_name, "L1": "ok"}
    matches = [key for key, name in KNOWN_BACKBONES.items() if name == model_name]
    if not matches:
        raise VersionValidationError(
            "L1", f"version model_name {model_name!r} is not a known backbone"
        )
    return {"backbone": matches[0], "model_name": model_name, "L1": "ok"}


def _probes(bundle) -> list:
    # format.py already decodes JSON-valued keys (fp_probes arrives as a list);
    # accept a raw JSON string too for direct readers.
    probes = bundle.meta["fp_probes"]
    return json.loads(probes) if isinstance(probes, str) else list(probes)


def _label_ids(bundle) -> list:
    if bundle.kind != "hard":
        return []
    return [int(t) for t in bundle.meta["label_token_ids"]]


def check_tokenizer(bundle, tokenizer) -> None:
    """L2 alone: needs only something that can ``encode`` (no backbone).

    The tokenizer must reproduce the packed token ids of the first probe; for a
    hard version, each answer code (``label_tokens``, e.g. A/B/C -- not the
    class names) must still be exactly one token, the packed id. Raises
    :class:`VersionValidationError`.
    """
    encoded = np.asarray(tokenizer.encode(_probes(bundle)[0])).ravel().tolist()
    packed = [int(t) for t in bundle.meta["fp_token_ids"]]
    if encoded != packed:
        raise VersionValidationError(
            "L2", f"tokenizer mismatch: packed {packed} != encoded {encoded}"
        )
    # token-form ids are a layout fact (canonical free rows), checked without a
    # backbone; the full L2 against a runtime repeats it with the probes above.
    if getattr(bundle, "token_form", False):
        from src.rsd.model_based.vocab_tokens import check_token_ids

        check_token_ids(bundle)
    if bundle.kind == "hard":
        # The head rows were taken for the answer codes, not the class names
        # (a multi-class version answers A/B/C for local/cloud/planning).
        tokens = bundle.meta["label_tokens"]
        tokens = json.loads(tokens) if isinstance(tokens, str) else list(tokens)
        label_ids = _label_ids(bundle)
        encoded = [np.asarray(tokenizer.encode(token)).ravel().tolist() for token in tokens]
        if any(len(ids) != 1 for ids in encoded) or label_ids != [int(ids[0]) for ids in encoded]:
            raise VersionValidationError(
                "L2",
                f"label tokens {label_ids} do not match the backbone's encoding of "
                f"{tokens} (each must be exactly one token)",
            )


def validate_against_runtime(
    bundle,
    runtime,
    *,
    backbone: Optional[str] = None,
    fp_min_cos: Optional[float] = None,
    env: Optional[Dict[str, str]] = None,
    l1_checked: bool = False,
) -> Dict[str, Any]:
    """Check ``bundle`` against ``runtime``: L1 name, L2 tokenizer, L3 fingerprints.

    Raises :class:`VersionValidationError` on the first failing level; returns
    the report dict on success (``{"L1": "ok", "L2": "ok", "L3_min_cos": ...,
    "hard_head_min_cos": ...}``) for logging and the version-info APIs.
    ``l1_checked``: the caller already ran :func:`check_model_name` against
    ``backbone`` (the registry does, before it patches a runtime), so L1 is
    not repeated.
    """
    min_cos = fingerprint_min_cos(env) if fp_min_cos is None else float(fp_min_cos)
    model_name = bundle.model_name

    # L1: model name -- the code's known-backbone table is the baseline.
    if l1_checked and backbone is not None:
        backbone_key = backbone
    else:
        backbone_key = check_model_name(bundle, backbone)["backbone"]

    report: Dict[str, Any] = {"backbone": backbone_key, "model_name": model_name, "L1": "ok"}

    # L2: the runtime's tokenizer must reproduce the packed token ids.
    # format.py already decodes JSON-valued keys (fp_probes / class_semantics
    # arrive as lists); accept a raw JSON string too for direct readers.
    probes = bundle.meta["fp_probes"]
    if isinstance(probes, str):
        probes = json.loads(probes)
    encoded = runtime.encode(probes[0]).ravel().tolist()
    packed = [int(t) for t in bundle.meta["fp_token_ids"]]
    if encoded != packed:
        raise VersionValidationError(
            "L2", f"tokenizer mismatch: packed {packed} != encoded {encoded}"
        )

    label_ids = []
    if bundle.kind == "hard":
        # The head rows were taken for the answer codes, not the class names
        # (a multi-class version answers A/B/C for local/cloud/planning).
        tokens = bundle.meta["label_tokens"]
        tokens = json.loads(tokens) if isinstance(tokens, str) else list(tokens)
        label_ids = [int(t) for t in bundle.meta["label_token_ids"]]
        encoded = [runtime.encode(token).ravel().tolist() for token in tokens]
        if any(len(ids) != 1 for ids in encoded) or label_ids != [int(ids[0]) for ids in encoded]:
            raise VersionValidationError(
                "L2",
                f"label tokens {label_ids} do not match the backbone's encoding of "
                f"{tokens} (each must be exactly one token)",
            )
    elif getattr(bundle, "token_form", False):
        # Token-form ids are layout, not tokenizer, facts -- checked without a
        # forward pass: free rows of this backbone, canonical order, no overlap.
        try:
            check_token_ids(bundle)
        except ValueError as exc:
            raise VersionValidationError("L2", str(exc)) from exc
    report["L2"] = "ok"

    # L3: hidden fingerprints -- one forward per probe (pure backbone).
    rows = fingerprint_rows(runtime, probes)
    cosines = [
        _cosine(row, reference)
        for row, reference in zip(rows, bundle.fp_hidden)
    ]
    min_probe_cos = min(cosines) if cosines else 1.0
    if min_probe_cos < min_cos:
        raise VersionValidationError(
            "L3",
            f"fingerprint min cos {min_probe_cos:.5f} < {min_cos} "
            "(wrong backbone, wrong export, or too-aggressive quantization)",
        )
    report["L3_min_cos"] = min_probe_cos

    # hard: the packed head rows must be the backbone's rows for the label
    # tokens (they stop matching when a quantized backbone is re-compressed).
    if bundle.kind == "hard":
        head_rows = np.asarray(
            runtime.label_rows(label_ids),
            dtype=np.float64,
        )
        head_cos = [
            _cosine(row, reference)
            for row, reference in zip(np.asarray(bundle.head_weight), head_rows)
        ]
        min_head_cos = min(head_cos)
        if min_head_cos < min_cos:
            raise VersionValidationError(
                "L3", f"hard head rows min cos {min_head_cos:.5f} < {min_cos}"
            )
        report["hard_head_min_cos"] = min_head_cos

    # token form: the rows written into the graph must read back as the packed
    # data (fp32 -> f16/bf16 rounding is the only allowed difference).
    if getattr(bundle, "token_form", False):
        report["vocab_rows_max_diff"] = check_vocab_rows(bundle, runtime)

    return report


# fp32 rows round to f16/bf16 constants: bf16 keeps ~3 decimal digits, so a
# generous tolerance still catches a wrong row (or a wrong constant) outright.
_ROW_RTOL = 1.0 / 64.0


def check_vocab_rows(bundle, runtime) -> float:
    """The written vocabulary rows read back equal the packed data.

    ``embed(soft_token_ids)`` returns the soft-prompt rows and
    ``label_rows(label_token_ids)`` the class rows (read from the lm_head
    weight), so both tables (the two
    independent constants of a split export, the shared one of a single-graph
    export) are covered without a forward pass. Returns the largest absolute
    deviation; raises :class:`VersionValidationError` when a row does not read
    back within the constant's rounding.
    """
    soft_ids = np.asarray(bundle.soft_token_ids, dtype=np.int64)
    label_ids = list(bundle.label_token_ids)
    read = {
        "the embedding table": (runtime.embed(soft_ids)[0], np.asarray(bundle.prompt)),
        "the lm_head rows": (
            np.asarray(runtime.label_rows(label_ids)),
            np.asarray(bundle.head_weight),
        ),
    }
    max_diff = 0.0
    for what, (got, want) in read.items():
        if got.shape != want.shape:
            raise VersionValidationError(
                "L3", f"{what}: read back {got.shape}, the version holds {want.shape}"
            )
        diff = float(np.abs(got.astype(np.float64) - want.astype(np.float64)).max())
        max_diff = max(max_diff, diff)
        scale = float(np.abs(want).max()) + 1e-6
        if diff > _ROW_RTOL * scale:
            raise VersionValidationError(
                "L3",
                f"{what}: written rows deviate by {diff:.5f} (> {_ROW_RTOL:.4f} x {scale:.4f}); "
                "the graph was patched with different data than the version holds",
            )
    return max_diff
