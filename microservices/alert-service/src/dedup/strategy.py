"""Deduplication strategies for alert processing."""

from __future__ import annotations

import abc
import hashlib
import logging
from typing import Any

from src.core.config import DedupConfig
from src.core.models import AlertEnvelope

logger = logging.getLogger(__name__)


def _extract_field(data: dict[str, Any], field_path: str) -> Any | None:
    """Extract a value from nested dict using dot-notation path.

    Search order for a path like 'metadata.poi_id':
      1. Navigate into data["metadata"]["poi_id"]
      2. Fallback: check data["dedup_metadata"]["poi_id"]
    """
    parts = field_path.split(".")

    # Primary: walk the path from the data root
    current: Any = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            current = None
            break

    if current is not None:
        return current

    # Fallback: try dedup_metadata for the leaf field
    leaf = parts[-1]
    dedup_meta = data.get("dedup_metadata")
    if isinstance(dedup_meta, dict) and leaf in dedup_meta:
        return dedup_meta[leaf]

    return None


class DedupStrategy(abc.ABC):
    """Abstract base class for dedup strategies."""

    @abc.abstractmethod
    def compute_key(
        self, envelope: AlertEnvelope, config: DedupConfig
    ) -> str | None:
        """Compute a dedup key. Returns None if dedup should be skipped."""


class FieldHashStrategy(DedupStrategy):
    """Hash specified fields to produce a dedup key."""

    def compute_key(
        self, envelope: AlertEnvelope, config: DedupConfig
    ) -> str | None:
        # Build source data: top-level payload merged with metadata context
        source = {**envelope.payload}
        source["metadata"] = envelope.metadata
        if "dedup_metadata" in envelope.payload:
            source["dedup_metadata"] = envelope.payload["dedup_metadata"]

        values: list[str] = []
        for field_path in config.fields:
            value = _extract_field(source, field_path)
            if value is None:
                if config.on_missing == "skip":
                    logger.warning(
                        "Dedup field '%s' missing for alert_type=%s, skipping dedup",
                        field_path,
                        envelope.alert_type,
                    )
                    return None
                # If on_missing is not skip, use empty string
                values.append("")
            else:
                values.append(str(value))

        raw = "+".join(values)

        hash_algo = config.hash.algorithm
        if hash_algo == "md5":
            digest = hashlib.md5(raw.encode()).hexdigest()  # noqa: S324
        else:
            digest = hashlib.sha1(raw.encode()).hexdigest()  # noqa: S324

        truncated = digest[: config.hash.truncate]

        return f"dedup:{envelope.alert_type}:{truncated}"


# Strategy registry
_STRATEGIES: dict[str, type[DedupStrategy]] = {
    "field_hash": FieldHashStrategy,
}


def get_strategy(name: str) -> DedupStrategy:
    """Get a dedup strategy by name."""
    cls = _STRATEGIES.get(name)
    if cls is None:
        raise ValueError(f"Unknown dedup strategy: {name}")
    return cls()
