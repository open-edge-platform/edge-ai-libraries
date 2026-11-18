# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""UI-facing classifier choices returned with a strategy detail."""

from __future__ import annotations

from typing import Any

from src.rsd.model_based.bundle import KIND_HARD
from src.rsd.model_based.hard_version import prompt_text
from src.rsd.model_based.settings import KNOWN_BACKBONES


def classifier_options(registry: Any) -> list[dict[str, Any]]:
    """Available model/version choices, with editable text for hard versions."""
    models = []
    for model in KNOWN_BACKBONES:
        versions = []
        for listing in registry.versions(model):
            item: dict[str, Any] = {"version": listing.version}
            if listing.bundle is not None:
                item["kind"] = listing.bundle.kind
                if listing.bundle.kind == KIND_HARD:
                    item["text"] = prompt_text(listing.bundle)
            else:
                item["kind"] = None
            if listing.error is not None:
                item["error"] = listing.error
            versions.append(item)
        models.append({"model": model, "versions": versions})
    return models
