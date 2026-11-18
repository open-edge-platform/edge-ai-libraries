# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Settings + builders for the model-based query classifiers.

Nothing here is exposed in ``config.yaml``. Facts that do not change per
deployment (the known backbones) are fixed in code; deployment knobs have
in-code defaults and read optional ``IR_*`` environment overrides so operators
can tune them without touching user routing config.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Optional

from src.exceptions import ConfigurationError
from src.rsd.model_based.base import QueryClassifier

_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_PROMPT_DIR = _PACKAGE_DIR / "prompts"

# Version shipped with the code for every known backbone, as
# prompts/<backbone>/<DEFAULT_VERSION>.rcv; "default" in a strategy refers to it.
DEFAULT_VERSION = "v1"

# Minimum L3 fingerprint cosine for a version to load on a backbone.
# IR_FP_MIN_COS overrides it; FP16 / INT8 pass while INT4 does not.
FINGERPRINT_MIN_COS = 0.98


def fingerprint_min_cos(env: Optional[Mapping[str, str]] = None) -> float:
    """Minimum L3 fingerprint cosine (``IR_FP_MIN_COS`` override supported)."""
    env = os.environ if env is None else env
    try:
        value = float(env.get("IR_FP_MIN_COS", FINGERPRINT_MIN_COS))
    except (TypeError, ValueError):
        return FINGERPRINT_MIN_COS
    return value if math.isfinite(value) and 0.0 <= value <= 1.0 else FINGERPRINT_MIN_COS


# Backbone name (as used in strategy params / artifact directories) -> official
# model name. The official name is the baseline for the .rcv model_name check.
KNOWN_BACKBONES: Dict[str, str] = {
    "qwen35-2b": "Qwen/Qwen3.5-2B",
    "qwen3-0.6b": "Qwen/Qwen3-0.6B",
    "llama3-1b": "meta-llama/Llama-3.2-1B-Instruct",
}
DEFAULT_BACKBONE = "qwen35-2b"

# Hard-prompt decision default: route to the most likely class unless its
# probability is below this.
HARD_THRESHOLD = 0.7

# Fixed probe texts for a version's backbone fingerprint (L3), shared by every
# packer: short / long, English / Chinese.
FP_PROBES = [
    "What is 2 + 2?",
    "用一句话解释什么是光合作用。",
    "Write a Python function that merges two sorted lists and explain its time complexity.",
    "请比较 Raft 和 Paxos 在成员变更、日志压缩和读一致性上的差异。",
]

# Multi-class rules: class i is answered with the single-token code CLASS_CODES[i].
CLASS_CODES = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAX_CLASSES = len(CLASS_CODES)


def default_backbone(env: Optional[Mapping[str, str]] = None) -> str:
    """Backbone used when a ModelBasedRule names none (``IR_BACKBONE`` overrides)."""
    env = os.environ if env is None else env
    name = env.get("IR_BACKBONE", DEFAULT_BACKBONE)
    if name not in KNOWN_BACKBONES:
        raise ConfigurationError(
            f"IR_BACKBONE={name!r} is not a known backbone; expected one of {sorted(KNOWN_BACKBONES)}"
        )
    return name


def default_version_path(backbone: str) -> Path:
    """The ``.rcv`` shipped for ``backbone`` (``prompts/<backbone>/v1.rcv``), i.e. its ``default``."""
    if backbone not in KNOWN_BACKBONES:
        raise ConfigurationError(
            f"Unknown backbone {backbone!r}; expected one of {sorted(KNOWN_BACKBONES)}"
        )
    return _DEFAULT_PROMPT_DIR / backbone / f"{DEFAULT_VERSION}.rcv"


def artifacts_dir(env: Optional[Mapping[str, str]] = None) -> Path:
    """Writable classifier-version root (``IR_ARTIFACTS_DIR`` override)."""
    env = os.environ if env is None else env
    return Path(env.get("IR_ARTIFACTS_DIR", "artifacts/router")).expanduser()


def swap_mode(env: Optional[Mapping[str, str]] = None) -> str:
    """Classifier backbone switch order: ``load_first`` or ``unload_first``."""
    env = os.environ if env is None else env
    value = env.get("IR_SWAP_MODE", "load_first").strip().lower()
    if value not in {"load_first", "unload_first"}:
        raise ConfigurationError(
            "IR_SWAP_MODE must be 'load_first' or 'unload_first'; "
            f"got {value!r}"
        )
    return value


def ov_model_env_var(backbone: str) -> str:
    """Per-backbone IR path variable, e.g. ``qwen3-0.6b`` -> ``IR_OV_MODEL_QWEN3_0P6B``."""
    return "IR_OV_MODEL_" + backbone.upper().replace("-", "_").replace(".", "P")


def resolve_ov_model_path(
    backbone: Optional[str] = None, env: Optional[Mapping[str, str]] = None
) -> str:
    """Return the OpenVINO IR directory for ``backbone`` (default backbone if omitted).

    ``IR_OV_MODEL_<BACKBONE>`` wins; the legacy ``IR_OV_MODEL`` is accepted as
    the path of the default backbone only.

    Raises:
        ConfigurationError: If the backbone is unknown, no path is set, or the
            path does not exist.
    """
    env = os.environ if env is None else env
    backbone = backbone or default_backbone(env)
    if backbone not in KNOWN_BACKBONES:
        raise ConfigurationError(f"Unknown backbone {backbone!r}; expected one of {sorted(KNOWN_BACKBONES)}")
    var = ov_model_env_var(backbone)
    explicit = env.get(var)
    if not explicit and backbone == default_backbone(env):
        var, explicit = "IR_OV_MODEL", env.get("IR_OV_MODEL")
    if not explicit:
        raise ConfigurationError(
            f"{ov_model_env_var(backbone)} / IR_OV_MODEL is not set. Set IR_OV_MODEL to the OpenVINO "
            "classifier model directory to enable model-based routing."
        )
    path = Path(explicit).expanduser()
    if not path.exists():
        raise ConfigurationError(
            f"{var} points to a missing directory: {path}. "
            "Set IR_OV_MODEL to the OpenVINO classifier model directory."
        )
    return str(path)


@dataclass
class ClassifierConfig:
    """How to build the OpenVINO hard-prompt classifier for a text prompt.

    ``labels`` are the class names reported in results (their order is the
    routing zone); ``label_tokens`` are the single tokens the model answers
    with, one per label (default: the labels themselves). ``system_prompt`` is
    the full prompt: for a multi-class rule, the user's prompt plus the answer key.
    """

    ov_model: str
    system_prompt: str
    labels: List[str]
    label_tokens: Optional[List[str]] = None
    device: str = "CPU"
    cache_size: int = 256
    threshold: float = HARD_THRESHOLD


# Opens the answer key appended to a hard prompt (see :func:`with_answer_key`).
ANSWER_KEY_INTRO = (
    "Respond with exactly one letter naming the category of the task, and nothing else:"
)


def with_answer_key(prompt: str, labels: List[str], codes: List[str]) -> str:
    """Append the code -> label answer key, so users describe classes by name only."""
    key = "\n".join(f"{code}: {label}" for code, label in zip(codes, labels))
    return f"{prompt.strip()}\n\n{ANSWER_KEY_INTRO}\n{key}"


def multiclass_classifier_config(
    model_path: str, labels: List[str], prompt: str, threshold: float = HARD_THRESHOLD
) -> ClassifierConfig:
    """Classifier config for a multi-class rule: the user's prompt plus the answer key."""
    if not 2 <= len(labels) <= MAX_CLASSES:
        raise ConfigurationError(
            f"a multi-class rule needs 2-{MAX_CLASSES} labels, got {len(labels)}"
        )
    codes = list(CLASS_CODES[: len(labels)])
    return ClassifierConfig(
        ov_model=model_path,
        system_prompt=with_answer_key(prompt, labels, codes),
        labels=list(labels),
        label_tokens=codes,
        device=os.environ.get("IR_DEVICE", "GPU"),
        cache_size=int(os.environ.get("IR_CACHE_SIZE", "256")),
        threshold=threshold,
    )


def build_classifier(cfg: ClassifierConfig) -> QueryClassifier:
    """Construct the OpenVINO hard-prompt classifier from ``cfg`` (imports OV lazily)."""
    from src.rsd.model_based.classifier import OVQwenClassifier

    return OVQwenClassifier(
        ov_model=cfg.ov_model,
        system_prompt=cfg.system_prompt,
        device=cfg.device,
        labels=cfg.labels,
        label_tokens=cfg.label_tokens,
        cache_size=cfg.cache_size,
        threshold=cfg.threshold,
    )
