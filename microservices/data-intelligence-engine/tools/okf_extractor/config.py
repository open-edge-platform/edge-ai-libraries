# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Standalone extractor configuration, shared by the REST service and CLI."""
from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import yaml

_DEFAULT_PATH = Path(__file__).resolve().parent / "config.yaml"


@dataclass(frozen=True)
class Config:
    raw: dict

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        p = Path(path) if path else _DEFAULT_PATH
        with open(p, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        if not isinstance(raw, dict):
            raise ValueError("Extractor configuration must be a YAML object")
        return cls(raw)

    @classmethod
    def from_env(cls, path: str | Path | None = None) -> "Config":
        """Only deployment configuration may choose the model endpoint/credentials.

        Task options deliberately cannot override these settings.
        """
        raw = deepcopy(cls.load(path or os.getenv("OKF_EXTRACTOR_CONFIG")).raw)
        for variable, key in (
            ("OKF_EXTRACTOR_LLM_BASE_URL", "base_url"),
            ("OKF_EXTRACTOR_LLM_MODEL", "model"),
            ("OKF_EXTRACTOR_LLM_API_KEY", "api_key"),
        ):
            value = os.getenv(variable)
            if value is not None:
                raw["llm"][key] = value
        return cls(raw)

    # thin typed accessors ---------------------------------------------------
    @property
    def llm(self) -> dict:
        return self.raw["llm"]

    @property
    def batch(self) -> dict:
        return self.raw["batch"]

    @property
    def tools(self) -> dict:
        return self.raw["tools"]

    @property
    def merge(self) -> dict:
        return self.raw["merge"]

    @property
    def instructions(self) -> dict:
        """Operator instruction constraints (empty = generate from task content)."""
        return self.raw.get("instructions") or {}

    @property
    def planning(self) -> dict:
        return self.raw.get("planning") or {}

    def prompt_path(self, which: str) -> str | None:
        """Absolute path to a prompt template, or None to use the bundled default.
        `which` in {"extract", "canonicalize"}."""
        p = (self.raw.get("prompts") or {}).get(which)
        if not p:
            return None
        pp = Path(p)
        return str(pp if pp.is_absolute() else _DEFAULT_PATH.parent / pp)

    # derived ----------------------------------------------------------------
    def read_input_budget(self) -> int:
        """THE Stage-1 batch cap (decision 7): how many tokens of read-tool output a
        single short-lived extract session may pull in before the read_* handlers
        hard-refuse and force write_concept. = context_window*safe_fraction - reserve."""
        w = int(self.llm["context_window"])
        b = self.batch
        budget = int(w * float(b["safe_fraction"])) - int(b["reserve_tokens"])
        if budget <= 0:
            raise ValueError("Extractor context window leaves no input token budget")
        return budget
