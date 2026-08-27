# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Configuration + builder for the vendored E/H intelligent query classifier.

Infrastructure knobs read optional ``IR_*`` environment overrides so operators
can tune them without touching user routing config; all have sane defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

_PACKAGE_DIR = Path(__file__).resolve().parent
_DEFAULT_PROMPT_DIR = _PACKAGE_DIR / "prompts"


@dataclass
class ClassifierConfig:
    """How to build the OpenVINO E/H classifier."""

    ov_model: str
    hf_model: str
    prompt_file: str = ""
    prompt_files: Dict[str, str] = field(default_factory=dict)
    device: str = "CPU"
    wrap: str = "任务："
    wraps: Dict[str, str] = field(default_factory=dict)
    labels: List[str] = field(default_factory=lambda: ["E", "H"])
    cache_size: int = 256


def default_classifier_config(model_path: str) -> ClassifierConfig:
    """Return the fixed default classifier config for ``model_path``.

    Device/cache-size accept ``IR_*`` env overrides; the model path is resolved by the caller
    """
    return ClassifierConfig(
        ov_model=model_path,
        hf_model=os.environ.get("IR_HF_MODEL", model_path),
        prompt_files={
            "zh": str(_DEFAULT_PROMPT_DIR / "zh.txt"),
            "en": str(_DEFAULT_PROMPT_DIR / "en.txt"),
        },
        device=os.environ.get("IR_DEVICE", "GPU"),
        wraps={"zh": "任务：", "en": "Task: "},
        cache_size=int(os.environ.get("IR_CACHE_SIZE", "256")),
    )


def build_classifier(cfg: ClassifierConfig):
    """Construct the OpenVINO classifier from ``cfg`` (imports OV lazily)."""
    from src.rsd.tools.ov_qwen import OVQwenClassifier

    prompt_files = dict(cfg.prompt_files)
    if not prompt_files and cfg.prompt_file:
        prompt_path = Path(cfg.prompt_file)
        inferred = {
            "zh": prompt_path.with_name("zh.txt"),
            "en": prompt_path.with_name("en.txt"),
        }
        if all(path.exists() for path in inferred.values()):
            prompt_files = {language: str(path) for language, path in inferred.items()}

    system_prompts = {
        language: Path(prompt_file).read_text(encoding="utf-8").strip()
        for language, prompt_file in prompt_files.items()
    }
    if cfg.prompt_file:
        system_prompt = Path(cfg.prompt_file).read_text(encoding="utf-8").strip()
    else:
        system_prompt = system_prompts.get("zh") or system_prompts.get("en") or ""

    return OVQwenClassifier(
        ov_model=cfg.ov_model,
        hf_model=cfg.hf_model,
        system_prompt=system_prompt,
        system_prompts=system_prompts,
        device=cfg.device,
        wrap=cfg.wrap,
        wraps=cfg.wraps,
        labels=cfg.labels,
        cache_size=cfg.cache_size,
    )
