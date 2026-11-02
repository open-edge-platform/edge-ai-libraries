# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import abc
import hashlib
import logging
from typing import Any

from src.schemas.request import DedupConfig

logger = logging.getLogger(__name__)


def _extract_field(data: dict[str, Any], field_path: str) -> Any | None:
    """Dot-notation nested field extractor with dedup_metadata fallback."""
    parts = field_path.split(".")
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            current = None
            break

    if current is not None:
        return current

    leaf = parts[-1]
    dedup_meta = data.get("dedup_metadata")
    if isinstance(dedup_meta, dict) and leaf in dedup_meta:
        return dedup_meta[leaf]
    return None


class DedupStrategy(abc.ABC):
    @abc.abstractmethod
    def compute_key(self, context: dict[str, Any], config: DedupConfig) -> str | None: ...


class FieldHashStrategy(DedupStrategy):
    def compute_key(self, context: dict[str, Any], config: DedupConfig) -> str | None:
        values: list[str] = []
        for field_path in config.fields:
            value = _extract_field(context, field_path)
            if value is None:
                if config.on_missing == "skip":
                    logger.warning("Dedup field '%s' missing — skipping dedup", field_path)
                    return None
                values.append("")
            else:
                values.append(str(value))

        raw = "+".join(values)
        algo = config.hash_algorithm
        digest = (
            hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()
            if algo == "md5"
            else hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()
        )
        truncated = digest[: config.hash_truncate]
        scope = context.get("alert_name", "unknown")
        return f"dedup:{scope}:{truncated}"


_STRATEGIES: dict[str, type[DedupStrategy]] = {
    "field_hash": FieldHashStrategy,
}


def get_strategy(name: str) -> DedupStrategy:
    cls = _STRATEGIES.get(name)
    if cls is None:
        raise ValueError(f"Unknown dedup strategy: {name}")
    return cls()
