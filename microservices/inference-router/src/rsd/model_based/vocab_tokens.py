# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Vocabulary-token layout: soft prompts and class heads as vocabulary rows.

A soft version (token form -- the only form) carries its trained data inside
the backbone vocabulary instead of multiplying it in outside the graph: the ``k`` soft
vectors become the embedding rows of ``k`` new "soft tokens" and the ``C``
head rows become the lm_head rows of ``C`` "class tokens" (both backbones tie
their embeddings, so one row serves the input and the output side). The router
then feeds a plain token-id sequence ``[soft ids][pad ids][query ids]`` and
reads the class logits straight out of ``logits[class_token_ids]`` -- which is
what makes later KV / prefix caching by token id possible.

The Qwen embedding matrices reserve more rows than the tokenizer uses; the
free rows continue the original vocabulary without resizing the matrix, so the
new ids never collide with real tokens. (A backbone without free rows --
llama3-1b -- gets its constants resized by the patch instead; see
:data:`LAYOUTS`.) The shipped (unregistered) tokenizer
cannot produce these ids -- a query containing a token string only tokenizes
to ordinary text. Registering the strings changes that deliberately
(:mod:`tools.register_vocab_tokens`): afterwards such a query tokenizes to the
token's id. The id assignment is a backbone constant: soft tokens first,
class tokens right after them::

    | original vocabulary | soft tokens (k) | class tokens (C) |
                          ^ first_free_id

Rows written into free-row space replace values that collapsed to a single
direction during pretraining, never anything the tokenizer emits.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.rsd.model_based.bundle import KIND_SOFT, ClassifierBundle
from src.rsd.model_based.settings import KNOWN_BACKBONES


@dataclass(frozen=True)
class VocabTokenLayout:
    """Where a backbone's free vocabulary rows start and end."""

    backbone: str
    first_free_id: int  # first id the tokenizer does not use
    rows: int  # embedding / lm_head matrix rows

    @property
    def free_ids(self) -> int:
        return self.rows - self.first_free_id


# Measured against the shipped IRs (2026-10-26): both Qwen tokenizers stop
# before the matrices do. qwen35-2b keeps two independent [248320, 2048] bf16
# constants (text_embeddings + language_model), qwen3-0.6b one shared
# [151936, 1024] fp16 constant.
#
# llama3-1b has no free rows (the tokenizer uses all 128256): its constants
# are fp16 and get **resized** by the patch -- 64 rows appended (ids
# 128256..128319), of which the version's soft + class tokens use the first
# ones. ``rows`` is the post-patch size, so ``free_ids`` counts the appended
# rows; the unwritten reserve rows stay zero and are never addressed.
LAYOUTS: Dict[str, VocabTokenLayout] = {
    "qwen35-2b": VocabTokenLayout("qwen35-2b", 248077, 248320),
    "qwen3-0.6b": VocabTokenLayout("qwen3-0.6b", 151669, 151936),
    "llama3-1b": VocabTokenLayout("llama3-1b", 128256, 128320),
}


def layout_for_backbone(backbone: str) -> VocabTokenLayout:
    """The layout of a known backbone."""
    try:
        return LAYOUTS[backbone]
    except KeyError:
        raise ValueError(
            f"no vocabulary-token layout for backbone {backbone!r}; "
            f"expected one of {sorted(LAYOUTS)}"
        ) from None


# Token strings, in canonical order (soft first, classes right after them).
# These are what :mod:`tools.register_vocab_tokens` adds to a tokenizer so the
# rows are addressable by string; the router itself addresses them by id and
# works with registered and unregistered tokenizers alike.
SOFT_TOKEN_FORMAT = "<|sp_{i}|>"
CLASS_TOKEN_FORMAT = "<|cls_{i}|>"


def soft_token_strings(k: int) -> List[str]:
    """The ``k`` soft-token strings, in the order of :func:`soft_token_ids`."""
    return [SOFT_TOKEN_FORMAT.format(i=i) for i in range(k)]


def class_token_strings(num_classes: int) -> List[str]:
    """The ``num_classes`` class-token strings, in the order of :func:`class_token_ids`."""
    return [CLASS_TOKEN_FORMAT.format(i=i) for i in range(num_classes)]


def backbone_of(bundle: ClassifierBundle) -> str:
    """The backbone key of a bundle, from its official ``model_name``."""
    for key, name in KNOWN_BACKBONES.items():
        if name == bundle.model_name:
            return key
    raise ValueError(f"version model_name {bundle.model_name!r} is not a known backbone")


def soft_token_ids(backbone: str, k: int) -> List[int]:
    """The ``k`` soft-token ids: the first free rows of the vocabulary."""
    layout = layout_for_backbone(backbone)
    _check_fit(layout, k, 0)
    return list(range(layout.first_free_id, layout.first_free_id + k))


def class_token_ids(backbone: str, k: int, num_classes: int) -> List[int]:
    """The ``num_classes`` class-token ids: the rows right after the soft tokens."""
    layout = layout_for_backbone(backbone)
    _check_fit(layout, k, num_classes)
    start = layout.first_free_id + k
    return list(range(start, start + num_classes))


def _check_fit(layout: VocabTokenLayout, k: int, num_classes: int) -> None:
    if k < 1 or num_classes < 0:
        raise ValueError(
            f"k must be >= 1 and num_classes >= 0, got k={k}, num_classes={num_classes}"
        )
    if k + num_classes > layout.free_ids:
        raise ValueError(
            f"{layout.backbone} has {layout.free_ids} free vocabulary rows; "
            f"{k} soft + {num_classes} class tokens do not fit"
        )


def check_token_ids(bundle: ClassifierBundle) -> None:
    """Check a token-form version's ids against its backbone's layout.

    No backbone needed: this is the layout half of L2 (the tokenizer half --
    probes reproduce -- is the regular L2). The ids must sit in the free rows
    and follow the canonical assignment, so a token id always means the same
    row on every deployment. Also accepts bundles that have not been through
    the format checks (e.g. built in memory): a missing id field is a clear
    error, not a ``TypeError``.
    """
    if not getattr(bundle, "token_form", False):
        raise ValueError("check_token_ids needs a token-form soft version")
    soft_ids, label_ids = bundle.soft_token_ids, bundle.label_token_ids
    if soft_ids is None or label_ids is None:
        missing = [
            name
            for name, ids in (("soft_token_ids", soft_ids), ("label_token_ids", label_ids))
            if ids is None
        ]
        raise ValueError(f"a token-form version needs both id fields, missing {missing}")
    backbone = backbone_of(bundle)
    layout = layout_for_backbone(backbone)
    k = int(np.asarray(bundle.prompt).shape[0])
    if len(label_ids) != bundle.num_classes:
        raise ValueError(
            f"label_token_ids must have num_classes={bundle.num_classes} entries, "
            f"got {len(label_ids)}"
        )
    _check_fit(layout, k, len(label_ids))
    expected_soft = soft_token_ids(backbone, k)
    expected_label = class_token_ids(backbone, k, len(label_ids))
    if list(soft_ids) != expected_soft:
        raise ValueError(
            f"soft_token_ids {list(soft_ids)} do not follow the {backbone} layout "
            f"(expected {expected_soft[0]}..{expected_soft[-1]})"
        )
    if list(label_ids) != expected_label:
        raise ValueError(
            f"label_token_ids {list(label_ids)} do not follow the {backbone} layout "
            f"(expected {expected_label[0]}..{expected_label[-1]}, right after the soft tokens)"
        )


@dataclass(frozen=True, eq=False)
class VocabTokenPatch:
    """The vocabulary rows a token-form version writes into a backbone's constants.

    The digest identifies the patched graph: runtimes are cached per
    ``(ir_dir, device, digest)`` because every distinct soft version is a
    distinct compiled model (way B -- the rows live in the graph).
    """

    soft_ids: Tuple[int, ...]
    soft_rows: np.ndarray  # [k, hidden] float32
    label_ids: Tuple[int, ...]
    label_rows: np.ndarray  # [num_classes, hidden] float32
    total_rows: Optional[int] = None  # resized tables grow to exactly this

    def __post_init__(self) -> None:
        # frozen dataclass: cache the digest once (it is read several times per
        # load -- registry cache key, classifier check, logging) via
        # object.__setattr__; SHA-256 over the rows is not free.
        object.__setattr__(self, "_digest", self._compute_digest())

    def _compute_digest(self) -> str:
        h = hashlib.sha256()
        h.update(np.asarray(self.soft_ids, dtype="<i8").tobytes())
        h.update(np.ascontiguousarray(self.soft_rows, dtype="<f4").tobytes())
        h.update(np.asarray(self.label_ids, dtype="<i8").tobytes())
        h.update(np.ascontiguousarray(self.label_rows, dtype="<f4").tobytes())
        return h.hexdigest()[:16]

    @property
    def digest(self) -> str:
        return self._digest

    @property
    def rows_by_id(self) -> Dict[int, np.ndarray]:
        """All rows to write, soft and class together, keyed by vocabulary id.

        Every table copy gets the same full set: the models are tied, so a
        row serves both sides, and duplicate copies of one table (the split
        single-graph export) stay identical.
        """
        rows = dict(zip(self.soft_ids, np.asarray(self.soft_rows, dtype=np.float32)))
        rows.update(zip(self.label_ids, np.asarray(self.label_rows, dtype=np.float32)))
        return rows


def token_patch(bundle: ClassifierBundle) -> Optional[VocabTokenPatch]:
    """The patch a soft (token-form) version needs; ``None`` for hard bundles."""
    if not getattr(bundle, "token_form", False):
        return None
    check_token_ids(bundle)
    return VocabTokenPatch(
        soft_ids=tuple(int(i) for i in bundle.soft_token_ids),
        soft_rows=np.asarray(bundle.prompt, dtype=np.float32),
        label_ids=tuple(int(i) for i in bundle.label_token_ids),
        label_rows=np.asarray(bundle.head_weight, dtype=np.float32),
    )


def add_token_ids(bundle: ClassifierBundle) -> ClassifierBundle:
    """A copy of a freshly assembled soft ``bundle`` with the canonical token ids added.

    How :mod:`tools.pack_rcv` gives a version its token form: slots and
    metadata are unchanged (the slot data is what gets written into the graph),
    only ``soft_token_ids`` / ``label_token_ids`` are added to the metadata.
    """
    if bundle.kind != KIND_SOFT:
        raise ValueError("only soft versions have a token form")
    if bundle.token_form:
        return bundle
    backbone = backbone_of(bundle)
    k = int(np.asarray(bundle.prompt).shape[0])
    meta = dict(bundle.meta)
    meta["soft_token_ids"] = soft_token_ids(backbone, k)
    meta["label_token_ids"] = class_token_ids(backbone, k, bundle.num_classes)
    patched = ClassifierBundle(
        kind=bundle.kind,
        prompt=bundle.prompt,
        head_weight=bundle.head_weight,
        head_bias=bundle.head_bias,
        fp_hidden=bundle.fp_hidden,
        meta=meta,
    )
    check_token_ids(patched)
    return patched
