# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Pack a hard-prompt classifier version from text, on the router's own backbone.

A hard version freezes a prompt into a ``.rcv`` file: the user's prompt plus the
answer key (``A: local`` ...), the categories, the threshold, and what the
backbone needs to check it later -- the head (the lm_head rows of the answer
codes) and the fingerprint of the probe texts, both computed with the backbone
it is packed on (``fp_ref = "openvino"``).

Versions are immutable and deduplicated by content: the same text, categories
and threshold on the same backbone map to the same version.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence

import numpy as np

from src.rsd.model_based.bundle import KIND_HARD, ClassifierBundle
from src.rsd.model_based.format import read_rcv
from src.rsd.model_based.settings import (
    ANSWER_KEY_INTRO,
    CLASS_CODES,
    FP_PROBES,
    KNOWN_BACKBONES,
    MAX_CLASSES,
    default_version_path,
    with_answer_key,
)
from src.rsd.model_based.validate import fingerprint_rows

logger = logging.getLogger(__name__)

FP_REF = "openvino"
_VERSION_FILE = re.compile(r"v([1-9][0-9]*)\.rcv\Z")


def content_hash(text: str, labels: Sequence[str], threshold: float) -> str:
    """Identity of a hard version's content: prompt text, categories, threshold.

    The text is taken stripped, as it is stored (see :func:`.settings.with_answer_key`),
    so the text read back from a version hashes to that version.
    """
    payload = json.dumps(
        {"text": text.strip(), "labels": list(labels), "threshold": float(threshold)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _version_files(directory: Path) -> Iterable[tuple[int, Path]]:
    if not directory.is_dir():
        return
    for path in directory.iterdir():
        match = _VERSION_FILE.fullmatch(path.name)
        if match and path.is_file():
            yield int(match.group(1)), path


def next_version(model: str, artifacts_root: Path) -> str:
    """``v{N+1}`` for the largest ``vN`` of ``model``, packaged or in the artifacts."""
    dirs = (default_version_path(model).parent, artifacts_root / model)
    numbers = [n for directory in dirs for n, _ in _version_files(directory)]
    return f"v{max(numbers, default=0) + 1}"


def find_hard_version(model: str, artifacts_root: Path, digest: str) -> Optional[str]:
    """The artifacts version of ``model`` whose content hash is ``digest``, if any."""
    for _, path in sorted(_version_files(artifacts_root / model)):
        try:
            bundle = read_rcv(path)
        except Exception as exc:  # noqa: BLE001 - one bad file must not block packing
            logger.warning("Skipping unreadable classifier version %s: %s", path, exc)
            continue
        if bundle.kind == KIND_HARD and bundle.meta.get("content_hash") == digest:
            return bundle.version
    return None


def build_hard_bundle(
    runtime,
    *,
    model: str,
    version: str,
    text: str,
    labels: Sequence[str],
    threshold: float,
    note: str = "",
) -> ClassifierBundle:
    """Assemble the hard version for ``text`` over ``labels`` on ``runtime``.

    Category ``i`` is answered with the single-token code ``CLASS_CODES[i]``;
    the answer key is appended to ``text``, so the prompt describes the
    categories by name only (as with a multi-class ``prompt_file``).
    """
    if model not in KNOWN_BACKBONES:
        raise ValueError(f"unknown backbone {model!r}; expected one of {sorted(KNOWN_BACKBONES)}")
    if not text.strip():
        raise ValueError("the prompt text is empty")
    if not 2 <= len(labels) <= MAX_CLASSES:
        raise ValueError(f"a hard version needs 2-{MAX_CLASSES} labels, got {len(labels)}")
    codes = list(CLASS_CODES[: len(labels)])
    code_ids = []
    for code in codes:
        # a tokenizer-level prefix (Llama's BOS) is not part of the code
        ids = np.asarray(runtime.strip_prompt_prefix(runtime.encode(code))).ravel().tolist()
        if len(ids) != 1:
            raise ValueError(f"answer code {code!r} is not a single token for this tokenizer")
        code_ids.append(int(ids[0]))

    meta = {
        "model_name": KNOWN_BACKBONES[model],
        "version": version,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "hidden": int(runtime.hidden_size),
        "fp_probes": list(FP_PROBES),
        "fp_ref": FP_REF,
        "fp_token_ids": [int(t) for t in np.asarray(runtime.encode(FP_PROBES[0])).ravel()],
        "num_classes": len(labels),
        # Without class_zones, each class is a zone named by class_semantics.
        "class_semantics": list(labels),
        "label_tokens": codes,
        "label_token_ids": code_ids,
        "threshold": float(threshold),
        # Hard queries go into the chat template whole; nothing is truncated.
        "text_max_tokens": 0,
        "truncation_side": "left",
        "render": {"template": f"{runtime.chat_style}_chat"},
        "content_hash": content_hash(text, labels, threshold),
    }
    if note:
        meta["note"] = note
    return ClassifierBundle(
        kind=KIND_HARD,
        prompt=with_answer_key(text, list(labels), codes),
        head_weight=np.asarray(runtime.label_rows(code_ids), dtype=np.float32),
        head_bias=np.zeros(len(labels), dtype=np.float32),
        fp_hidden=np.asarray(fingerprint_rows(runtime, FP_PROBES), dtype=np.float32),
        meta=meta,
    )


def prompt_text(bundle: ClassifierBundle) -> str:
    """The prompt text of a hard version as the user wrote it, without the answer key.

    The text is stored stripped (see :func:`content_hash`); a hard prompt
    without an appended answer key is returned whole.
    """
    head, sep, _ = bundle.prompt.rpartition(f"\n\n{ANSWER_KEY_INTRO}\n")
    return head if sep else bundle.prompt
