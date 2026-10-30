# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Publish sinks — the closed set of probe destinations.

A sink takes a tick's aggregates and writes them somewhere. There are exactly
two: :class:`MetadataSink` (into the live ``ProviderMetadata`` for routing) and
:class:`FileSink` (append a JSONL history). No sink is per-backend.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict

from src.config.loader import resolve_workspace_dir
from src.providers.base import ProviderMetadata
from src.providers.probes.spec import DEFAULT_FILE_MAX_ENTRIES


if TYPE_CHECKING:  # avoid a runtime import cycle probe <-> publish
    from src.providers.probes.probe import ProviderProbe


logger = logging.getLogger(__name__)

# Segments of the metadata dotted path that map to typed fields on
# ``ProviderMetadata`` rather than into its free-form ``attributes`` dict.
_KNOWN_FIELDS = ("attributes", "capability", "performance", "cost", "labels")

# Characters that would break a dotted path or collide with Prometheus label
# syntax; stripped/replaced when a parsed name is used as a metadata key.
_LABEL_BLOCK = re.compile(r"\{[^}]*\}")
_UNSAFE_CHARS = re.compile(r"[.:\s]")


class Sink:
    """Base sink interface: ``emit(probe, aggregates)`` per tick."""

    def emit(self, probe: "ProviderProbe", aggregates: Dict[str, float]) -> None:
        raise NotImplementedError


class MetadataSink(Sink):
    """Write each aggregate to ``<prefix>.<name>`` in the live provider metadata.

    Because the strategy layer rebuilds ``{**provider.metadata.to_dict()}`` on
    every route, values written here are seen by the very next routing decision
    with no cache and no invalidation.
    """

    def __init__(self, prefix: str):
        self.prefix = prefix

    def emit(self, probe: "ProviderProbe", aggregates: Dict[str, float]) -> None:
        metadata = getattr(probe.host, "metadata", None)
        if not isinstance(metadata, ProviderMetadata):
            # A pass-through provider may not carry routing metadata; the
            # metadata sink is a no-op there (use a file sink instead).
            return
        for name, value in aggregates.items():
            dotted = f"{self.prefix}.{self._normalize(name)}"
            _set_metadata_path(metadata, dotted, value)

    @staticmethod
    def _normalize(name: str) -> str:
        """Make a parsed field name safe as a dotted-path segment.

        Drops Prometheus ``{label="..."}`` blocks and replaces ``.``/``:``/space
        so a raw metric name never fractures the path or shadows a nested key.
        """
        cleaned = _LABEL_BLOCK.sub("", name)
        cleaned = _UNSAFE_CHARS.sub("_", cleaned).strip("_")
        return cleaned or "value"


class FileSink(Sink):
    """Append a JSONL record ``{ts, provider, probe, aggregates}`` per tick.

    A durable history for dashboards/offline analysis, independent of process
    memory. The parent directory is created on first write.

    A **relative** ``path`` is resolved against the runtime workspace directory
    (the ``config.yaml`` dir — see :func:`resolve_workspace_dir`), not the process
    CWD. This keeps the output location stable regardless of where the server is
    launched from: in Docker the CWD already *is* the workspace, but in local runs
    the CWD is typically the project root, and resolving against CWD there would
    scatter files (or double-nest a ``workspace/`` prefix). Absolute paths are
    used verbatim.

    A probe runs forever, so the history is capped at ``max_entries`` records:
    the sink retains the most recent ``max_entries`` lines and drops older ones.
    To avoid rewriting the whole file on every tick at steady state, compaction
    runs in batches — the file is allowed to overshoot by a small slack, then
    trimmed back to exactly ``max_entries``. Pass ``max_entries <= 0`` to disable
    the cap (unbounded growth).
    """

    def __init__(self, path: str, max_entries: int = DEFAULT_FILE_MAX_ENTRIES):
        candidate = Path(path)
        self.path = candidate if candidate.is_absolute() else resolve_workspace_dir() / candidate
        # <= 0 disables the cap.
        self.max_entries = max_entries if max_entries > 0 else 0
        # Overshoot budget before a compaction: ~10% of the cap (min 1) so a
        # 10k-entry history is rewritten roughly once every 1k ticks, not every
        # tick.
        self._slack = max(1, self.max_entries // 10) if self.max_entries else 0
        self._ensured = False
        self._count = 0  # lines currently on disk (initialized in _ensure())

    def emit(self, probe: "ProviderProbe", aggregates: Dict[str, float]) -> None:
        record = {
            "ts": time.time(),
            "provider": getattr(probe.host, "name", None),
            "probe": probe.spec.name,
            "aggregates": aggregates,
        }
        try:
            self._ensure()
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
            self._count += 1
            if self.max_entries and self._count > self.max_entries + self._slack:
                self._trim()
        except OSError as exc:
            logger.warning("probe file sink write failed (%s): %s", self.path, exc)

    def _ensure(self) -> None:
        """Create the parent dir and seed the on-disk line count, once.

        Counting existing lines on first write lets the cap survive a restart:
        an already-full history is trimmed on the next overshoot rather than
        growing by another full ``max_entries`` before the sink notices it.
        """
        if self._ensured:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._count = self._count_lines() if self.max_entries else 0
        self._ensured = True

    def _count_lines(self) -> int:
        if not self.path.exists():
            return 0
        count = 0
        with self.path.open("rb") as handle:
            for _ in handle:
                count += 1
        return count

    def _trim(self) -> None:
        """Rewrite the file keeping only the most recent ``max_entries`` records.

        Written to a sibling temp file then atomically renamed, so a crash mid-
        compaction can never leave a truncated history.
        """
        with self.path.open("r", encoding="utf-8") as handle:
            lines = handle.readlines()
        keep = lines[-self.max_entries:]
        tmp_path = self.path.with_name(f"{self.path.name}.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.writelines(keep)
        os.replace(tmp_path, self.path)
        self._count = len(keep)


def _set_metadata_path(metadata: ProviderMetadata, dotted: str, value: Any) -> None:
    """Set ``value`` at ``dotted`` inside a live ``ProviderMetadata``.

    The first path segment selects the container: a recognised typed field
    (``attributes``/``capability``/``performance``/``cost``) or, for anything
    else, the free-form ``attributes`` dict (so ``probe.x`` lands in
    ``attributes['probe']['x']``). Intermediate dicts are created as needed.

    Note: ``ProviderMetadata.to_dict()`` flattens ``attributes`` to the top
    level, so a value written under ``attributes.probe.foo`` is read by routing
    as ``probe.foo``. To feed a routing field directly (e.g. the
    ``performance.*`` namespace read by ``PerformanceBased``) set the sink's
    ``prefix`` to that field.
    """
    parts = dotted.split(".")
    head, rest = parts[0], parts[1:]

    if head == "attributes":
        container = metadata.attributes
    elif head == "capability":
        container = metadata.capability
    elif head == "performance":
        # Typed as Optional[float]; promote to a dict so nested metrics fit.
        if not isinstance(metadata.performance, dict):
            metadata.performance = {}
        container = metadata.performance
    elif head == "cost":
        if not isinstance(metadata.cost, dict):
            metadata.cost = {}
        container = metadata.cost
    else:
        # Unrecognised root → treat the whole path as living in attributes.
        container = metadata.attributes
        rest = parts

    if not rest:
        return

    for part in rest[:-1]:
        nxt = container.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            container[part] = nxt
        container = nxt
    container[rest[-1]] = value


def build_sink(spec) -> Sink:
    """Construct the concrete sink for one ``PublishSpec``."""
    if spec.to == "metadata":
        return MetadataSink(prefix=spec.prefix)
    if spec.to == "file":
        return FileSink(path=spec.path, max_entries=spec.max_entries)
    raise ValueError(f"unknown publish target: {spec.to!r}")
